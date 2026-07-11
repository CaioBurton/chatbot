"""PATCH /documents/{doc_id} — corrects doc_type/edital_ref/edital_cycle on an
already-indexed document and re-triggers ingestion so every chunk's Qdrant
payload reflects the fix.

Fully mocked: no live Postgres/Qdrant required. The DB session's `execute` is
driven by `side_effect` because two different queries hit it per request —
`get_current_user`'s `select(User)` (via `require_admin`) and the route's own
`select(Document)` — and a single fixed `return_value` (as in
`make_mock_db`) cannot distinguish between them.
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.db.postgres import get_db
from app.main import app as _app
from app.models.document import Document
from app.models.user import User


def _admin_user() -> User:
    user = User()
    user.id = uuid4()
    user.email = "ci-tester@example.test"
    user.password_hash = "unused"
    user.role = "admin"
    return user


def _document(**overrides) -> Document:
    doc = Document()
    doc.id = uuid4()
    doc.filename = "stored-file.pdf"
    doc.original_name = "Edital Original.pdf"
    doc.display_name = "Edital Original"
    doc.source_url = None
    doc.doc_type = "edital"
    doc.edital_ref = None
    doc.edital_cycle = "2024/2025"
    doc.status = "active"
    doc.error_message = None
    for key, value in overrides.items():
        setattr(doc, key, value)
    return doc


def _session_returning(document_result) -> AsyncMock:
    """DB session whose first execute() (the admin lookup) returns the admin
    user, whose second (the route's own select) returns `document_result`,
    and whose third (the `DELETE FROM chunks` text() statement, only reached
    on the success path) is a no-op."""
    user_result = MagicMock()
    user_result.scalar_one_or_none.return_value = _admin_user()

    doc_result = MagicMock()
    doc_result.scalar_one_or_none.return_value = document_result

    session = AsyncMock()
    session.execute = AsyncMock(side_effect=[user_result, doc_result, MagicMock()])
    session.commit = AsyncMock()
    return session


def _override_get_db(session):
    async def _override():
        yield session

    return _override


async def test_patch_updates_metadata_and_reindexes(async_client, test_jwt, tmp_path):
    doc = _document()
    session = _session_returning(doc)
    _app.dependency_overrides[get_db] = _override_get_db(session)

    upload_dir = tmp_path
    (upload_dir / doc.filename).write_bytes(b"%PDF-1.4 fake")

    qdrant_mock = MagicMock()
    qdrant_mock.delete = AsyncMock()
    process_document_mock = AsyncMock()

    try:
        with patch("app.api.routes.documents._UPLOAD_DIR", upload_dir), \
             patch("app.api.routes.documents.get_qdrant_client", return_value=qdrant_mock), \
             patch("app.api.routes.documents.process_document", process_document_mock):
            resp = await async_client.patch(
                f"/documents/{doc.id}",
                json={"doc_type": "aditivo", "edital_ref": "Edital PIBIC 2025/2026", "edital_cycle": "2025/2026"},
                headers={"Authorization": f"Bearer {test_jwt}"},
            )
    finally:
        _app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["doc_type"] == "aditivo"
    assert body["edital_ref"] == "Edital PIBIC 2025/2026"
    assert body["edital_cycle"] == "2025/2026"

    # Old chunks purged before re-ingestion is scheduled.
    qdrant_mock.delete.assert_awaited_once()
    process_document_mock.assert_awaited_once()
    assert doc.status == "uploaded"
    assert doc.error_message is None


async def test_patch_clears_optional_fields_with_blank_strings(async_client, test_jwt, tmp_path):
    doc = _document(doc_type="aditivo", edital_ref="Edital antigo", edital_cycle="2024/2025")
    session = _session_returning(doc)
    _app.dependency_overrides[get_db] = _override_get_db(session)

    (tmp_path / doc.filename).write_bytes(b"%PDF-1.4 fake")

    try:
        with patch("app.api.routes.documents._UPLOAD_DIR", tmp_path), \
             patch("app.api.routes.documents.get_qdrant_client", return_value=MagicMock(delete=AsyncMock())), \
             patch("app.api.routes.documents.process_document", AsyncMock()):
            resp = await async_client.patch(
                f"/documents/{doc.id}",
                json={"doc_type": "aditivo", "edital_ref": "  ", "edital_cycle": ""},
                headers={"Authorization": f"Bearer {test_jwt}"},
            )
    finally:
        _app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["edital_ref"] is None
    assert body["edital_cycle"] is None


async def test_patch_returns_404_when_document_missing(async_client, test_jwt):
    session = _session_returning(None)
    _app.dependency_overrides[get_db] = _override_get_db(session)

    try:
        resp = await async_client.patch(
            f"/documents/{uuid4()}",
            json={"doc_type": "edital"},
            headers={"Authorization": f"Bearer {test_jwt}"},
        )
    finally:
        _app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 404


async def test_patch_returns_409_when_document_processing(async_client, test_jwt):
    doc = _document(status="processing")
    session = _session_returning(doc)
    _app.dependency_overrides[get_db] = _override_get_db(session)

    try:
        resp = await async_client.patch(
            f"/documents/{doc.id}",
            json={"doc_type": "edital"},
            headers={"Authorization": f"Bearer {test_jwt}"},
        )
    finally:
        _app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 409


async def test_patch_returns_404_when_source_file_missing(async_client, test_jwt, tmp_path):
    doc = _document()
    session = _session_returning(doc)
    _app.dependency_overrides[get_db] = _override_get_db(session)

    try:
        # tmp_path is empty — doc.filename was never written to disk.
        with patch("app.api.routes.documents._UPLOAD_DIR", tmp_path):
            resp = await async_client.patch(
                f"/documents/{doc.id}",
                json={"doc_type": "edital"},
                headers={"Authorization": f"Bearer {test_jwt}"},
            )
    finally:
        _app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 404
