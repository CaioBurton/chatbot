from app.core.document_names import format_document_display_name, resolve_document_display_name


def test_resolve_document_display_name_prefers_metadata_title():
    pages = [{"page_number": 1, "text": "EDITAL PIBIC 2025-2026\nUniversidade Federal do Piaui"}]

    display_name = resolve_document_display_name(
        original_name="arquivo.pdf",
        pages=pages,
        metadata_title="Aditivo 1 - ICV 2025-2026",
    )

    assert display_name == "Aditivo 1 - ICV 2025-2026"


def test_resolve_document_display_name_uses_first_page_title_when_metadata_missing():
    pages = [
        {
            "page_number": 1,
            "text": (
                "UNIVERSIDADE FEDERAL DO PIAUI\n"
                "ADITIVO 1 - ICV 2025-2026\n"
                "PROGRAMA DE INICIACAO CIENTIFICA VOLUNTARIA\n"
                "As inscricoes ocorrerao via SIGAA."
            ),
        }
    ]

    display_name = resolve_document_display_name(
        original_name="Aditivo_1_-_ICV_2025-2026_assinado_assinado.pdf",
        pages=pages,
    )

    assert display_name == "ADITIVO 1 - ICV 2025-2026 - PROGRAMA DE INICIACAO CIENTIFICA VOLUNTARIA"


def test_resolve_document_display_name_falls_back_when_first_page_is_paragraph_text():
    pages = [
        {
            "page_number": 1,
            "text": (
                "Este documento estabelece procedimentos para execucao das atividades "
                "administrativas da instituicao e nao apresenta um titulo formal no topo da pagina."
            ),
        }
    ]

    display_name = resolve_document_display_name(
        original_name="Aditivo_1_-_ICV_2025-2026_assinado_assinado.pdf",
        pages=pages,
    )

    assert display_name == "Aditivo 1 - ICV 2025-2026"


def test_format_document_display_name_removes_storage_noise():
    assert (
        format_document_display_name(
            "123e4567-e89b-12d3-a456-426614174000_Aditivo_1_-_ICV_2025-2026_assinado_assinado.pdf"
        )
        == "Aditivo 1 - ICV 2025-2026"
    )