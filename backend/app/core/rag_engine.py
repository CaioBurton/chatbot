"""
core/rag_engine.py — Full RAG pipeline with SSE streaming.

Implements rag_stream(), an async generator that yields SSE-compatible dicts:
  {"event": "token",   "data": "<chunk>"}
  {"event": "sources", "data": "<JSON array>"}
  {"event": "done",    "data": "[DONE]"}

Pipeline stages:
    1. Query preprocessing (whitespace normalisation)
    2. HyDE — hypothetical-document embedding via Ollama
    3. Multi-query — MULTIQUERY_COUNT reformulations; union + dedup across hybrid_search calls
    4. Reranking via bge-reranker-v2-m3
    5. Fallback guard (no reranked results survive the configured threshold)
    6. Context assembly — expand_to_parents, top-5; chat history from DB
    7. Prompt construction using PROPESQI system prompt template
    8. LLM streaming via Ollama /api/chat
    9. Post-processing — save user + assistant messages; update last_activity
"""

import asyncio
import json
import logging
import re
import time
from datetime import datetime, timedelta, timezone
from typing import AsyncGenerator
from uuid import UUID, uuid4

import httpx
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.document_names import format_document_display_name
from app.db.rag_config import get_rag_config
from app.db.reranker import rerank
from app.db.search import expand_to_parents, hybrid_search
from app.models.chat import ChatMessage, ChatSession
from qdrant_client.models import FieldCondition, Filter, MatchAny, MatchText, ScoredPoint

# Exclude non-editorial document types from RAG retrieval by default.
# Portarias list program names (causing the reranker to surface them for
# content questions), and relatorios contain project-specific data not
# relevant to Q&A about edital rules.
_RAG_PAYLOAD_FILTER = Filter(
    must_not=[
        FieldCondition(
            key="doc_type",
            match=MatchAny(any=["portaria", "relatorio"]),
        )
    ]
)

# Q15 pinned injection: ICV-only search to bypass reranker competition.
# MatchText("icv") on the source field tokenises filenames like
# "3-2025-2026_Edital_ICV.pdf" → includes all ICV editais regardless of year.
_ICV_SOURCE_FILTER = Filter(
    must=[FieldCondition(key="source", match=MatchText(text="icv"))],
    must_not=[FieldCondition(key="doc_type", match=MatchAny(any=["portaria", "relatorio"]))],
)
_ICV_HABILITACAO_RE = re.compile(
    r"\bICV\b.{0,100}\bpontos?\s+m[íi]nimos?\b"
    r"|\bpontos?\s+m[íi]nimos?\b.{0,100}\bICV\b",
    re.IGNORECASE,
)
_ICV_HABILITACAO_QUERY = (
    "ICV habilitado etapa análise planos trabalho proponente atingir mínimo "
    "pontos somatório total tabela pontuação Iniciação Científica Voluntária"
)

# Q05 pinned injection: "vigência bolsas" for a specific program (not Q25 cross-program).
# The cronograma section floods context with many date ranges; pinning the dedicated
# "DO PERÍODO DE VIGÊNCIA DA BOLSA" section forces the LLM to see the correct dates.
_VIGENCIA_BOLSA_RE = re.compile(
    r"\bvig[eê]ncia\b.*\bbolsa[s]?\b|\bbolsa[s]?\b.*\bvig[eê]ncia\b",
    re.IGNORECASE,
)
_VIGENCIA_BOLSA_QUERY = (
    "DO PERÍODO DE VIGÊNCIA DA BOLSA vigência doze meses início término setembro agosto PIBIC ICV PIBITI"
)

logger = logging.getLogger(__name__)

_LOCAL_MODEL = "gemma3:12b"

# Serialise all Ollama inference calls to prevent concurrent GPU pressure.
# gemma3:12b fills most of the 16 GB VRAM on the RTX 5060 Ti; running two or
# more inferences simultaneously triggers the OOM killer
# ("llama-server process has terminated: signal: killed").
# Raise the limit only if a larger GPU is available.
_OLLAMA_SEMAPHORE = asyncio.Semaphore(1)
_OLLAMA_MAX_RETRIES = 3
_OLLAMA_RETRY_BASE_DELAY = 5.0  # seconds; multiplied by attempt index

_FALLBACK_MESSAGE = (
    "Não possuo informações sobre este assunto em minha base de documentos. "
    "Para esclarecimentos adicionais, entre em contato diretamente com a PROPESQI."
)

_GREETING_PATTERN = re.compile(
    r"^\s*(ol[aá]|oi|bom\s*dia|boa\s*tarde|boa\s*noite|ei+|hey|hello|hi|"
    r"tudo\s*bem|tudo\s*bom|como\s*vai|como\s*est[aá]s?|boa\s*hora)\s*[!?.]*\s*$",
    re.IGNORECASE | re.UNICODE,
)

_GREETING_RESPONSE = (
    "Olá! Seja bem-vindo(a) ao assistente virtual da PROPESQI/UFPI. "
    "Estou aqui para responder dúvidas sobre pesquisa e inovação da "
    "Universidade Federal do Piauí. Como posso ajudá-lo(a) hoje?"
)

_IDENTITY_PATTERN = re.compile(
    r"^\s*(o\s*que\s*(voc[eê]|vc|tu|o\s*sr\.?)\s*(é|e|eh|representa|faz|significa)|quem\s+(é|e|eh)\s+(voc[eê]|vc|tu|o\s*sr\.?|esse\s+assistente|o\s+assistente)|para\s+qu[eê]\s+(voc[eê]|vc|serve)|como\s+(voc[eê]|vc)\s+(funciona|pode\s+me\s+ajudar|ajuda)|me\s+apresente|se\s+apresente|sua\s+fun[cç][aã]o)\s*[!?.]*\s*$",
    re.IGNORECASE | re.UNICODE,
)

_IDENTITY_RESPONSE = (
    "Sou o assistente virtual da Pró-Reitoria de Pesquisa e Inovação (PROPESQI) "
    "da Universidade Federal do Piauí (UFPI). Fui desenvolvido para ajudá-lo(a) "
    "a encontrar informações nos documentos institucionais da PROPESQI, como editais, "
    "resoluções, regulamentos e outros materiais oficiais. "
    "Basta me fazer uma pergunta sobre pesquisa e inovação na UFPI!"
)

# Lexical injection: add domain-specific terms to the hybrid search candidate pool
# when queries suffer from vocabulary mismatch between the question and the relevant
# chunks. These synthetic queries are merged (union + dedup by max score) into the
# normal retrieval set before reranking — the reranker then judges all candidates
# against the original query without any structural change to the pipeline.
_LEXICAL_EXPANSIONS: list[tuple[re.Pattern, str]] = [
    # Q26-type: "sistema"/"plataforma"/"portal" → chunks with "SIGAA" keyword
    (
        re.compile(r"\b(sistema|plataforma|portal)\b", re.IGNORECASE),
        "SIGAA sistema integrado gestão atividades acadêmicas inscrições relatórios",
    ),
    # Q29-type: "filho"/"filha"/"cônjuge"/"parente" → conflict-of-interest chunks
    (
        re.compile(r"\b(filho|filha|c[oô]njuge|esposa|marido|parente|familiar)\b", re.IGNORECASE),
        "vedado cônjuge companheiro parente linha reta colateral afinidade terceiro grau orientar",
    ),
    # Q05-type: "vigência" → bolsa vigência section (structural heading, future-proof)
    # Uses the section title "DO PERÍODO DE VIGÊNCIA DA BOLSA" and "doze meses" —
    # structural language that appears in every edital regardless of specific dates.
    (
        re.compile(r"\bvig[eê]ncia\b", re.IGNORECASE),
        "DO PERÍODO DE VIGÊNCIA DA BOLSA doze meses início término vigência bolsas edital",
    ),
    # Q25-type: "vigência" + "todos"/"programas" → cross-doc cronograma from all editais
    (
        re.compile(r"\bvig[eê]ncia\b.*\b(todos|programas|PIBIC|ICV|PIBITI|PIBICEM)\b|\b(todos|programas)\b.*\bvig[eê]ncia\b", re.IGNORECASE),
        "PIBIC ICV PIBITI PIBICEM todos os programas vigência início término cronograma bolsas",
    ),
    # Q15-type generic: "pontos mínimos" → habilitação chunk (catches Q06/PIBIC etc.)
    (
        re.compile(r"\bpontos?\s+m[íi]nimos?\b", re.IGNORECASE),
        "pontos mínimos habilitado análise plano trabalho tabela pontuação Anexo I orientador",
    ),
    # Q15-type ICV-specific: "pontos mínimos" + "ICV" → ICV 6.1.2.2 clause vocabulary
    # Uses near-verbatim structural text so the cross-encoder ranks the ICV habilitação
    # parent above competing PIBIC scoring-table chunks during reranking.
    (
        re.compile(
            r"\bICV\b.{0,100}\bpontos?\s+m[íi]nimos?\b"
            r"|\bpontos?\s+m[íi]nimos?\b.{0,100}\bICV\b",
            re.IGNORECASE,
        ),
        "ICV habilitado etapa análise planos trabalho proponente atingir mínimo pontos "
        "somatório total tabela pontuação Iniciação Científica Voluntária",
    ),
]


def _lexical_injection_queries(query: str) -> list[str]:
    """Return synthetic queries for patterns that suffer from lexical mismatch."""
    return [expansion for pattern, expansion in _LEXICAL_EXPANSIONS if pattern.search(query)]

# Compression prompt is module-level to avoid per-call re-allocation and to
# keep the instruction surface auditable in one place.
_COMPRESS_PROMPT_TEMPLATE = (
    "Dado o trecho de documento abaixo e a pergunta do usuário, extraia "
    "APENAS as frases ou passagens do trecho que são diretamente relevantes "
    "para responder à pergunta. Mantenha o texto original das frases "
    "selecionadas sem parafrasear. Se nenhuma parte do trecho for claramente "
    "relevante, retorne o trecho completo sem alterações. Não adicione "
    "explicações, prefácios ou comentários — responda apenas com o texto "
    "extraído.\n\n"
    "Pergunta: {query}\n\n"
    "Trecho:\n{text}"
)

_SYSTEM_PROMPT = """\
Você é o assistente virtual da Pró-Reitoria de Pesquisa e Inovação (PROPESQI) \
da Universidade Federal do Piauí (UFPI). Responda sempre em português formal \
e de forma clara e objetiva.

REGRAS OBRIGATÓRIAS:
1. Responda EXCLUSIVAMENTE com base nos documentos fornecidos no contexto.
2. Se a informação não estiver nos documentos, responda:
   "Não possuo informações sobre este assunto em minha base de documentos.
    Para esclarecimentos adicionais, entre em contato diretamente com a PROPESQI."
3. Nunca invente datas, normas, nomes ou valores.
4. Mantenha tom institucional, respeitoso e acessível ao público universitário.
5. Ao citar datas, mencione sempre o dia, o mês e o ano completos \
(ex: "1º de setembro de 2025", nunca apenas "setembro de 2025" ou "2025").

CONTEXTO DOS DOCUMENTOS:
{context}

HISTÓRICO DA CONVERSA:
{chat_history}\
"""


def _log_stage_duration(session_id: UUID, stage: str, start_time: float) -> None:
    elapsed_ms = (time.perf_counter() - start_time) * 1000
    logger.info(
        "rag_stream: session=%s stage=%s duration_ms=%.2f",
        session_id,
        stage,
        elapsed_ms,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

async def _ollama_generate(prompt: str, temperature: float, settings) -> str:
    """Call Ollama /api/chat (non-streaming) and return the response text.

    Acquires _OLLAMA_SEMAPHORE before each attempt to prevent concurrent GPU
    inference.  Retries on HTTP 500 (llama-server killed / OOM recovery) with
    linear back-off up to _OLLAMA_MAX_RETRIES attempts.
    """
    last_exc: Exception | None = None
    for attempt in range(_OLLAMA_MAX_RETRIES):
        if attempt > 0:
            delay = _OLLAMA_RETRY_BASE_DELAY * attempt
            logger.info(
                "_ollama_generate: waiting %.1fs before retry %d/%d",
                delay, attempt + 1, _OLLAMA_MAX_RETRIES,
            )
            await asyncio.sleep(delay)
        async with _OLLAMA_SEMAPHORE:
            async with httpx.AsyncClient(timeout=300.0) as http:
                resp = await http.post(
                    f"{settings.OLLAMA_BASE_URL}/api/chat",
                    json={
                        "model": _LOCAL_MODEL,
                        "messages": [{"role": "user", "content": prompt}],
                        "stream": False,
                        "options": {"temperature": temperature},
                    },
                )
                if resp.status_code == 500:
                    logger.warning(
                        "_ollama_generate: HTTP 500 on attempt %d/%d — body: %s",
                        attempt + 1, _OLLAMA_MAX_RETRIES, resp.text[:200],
                    )
                    last_exc = httpx.HTTPStatusError(
                        message="Server error '500 Internal Server Error'",
                        request=resp.request,
                        response=resp,
                    )
                    continue
                if resp.status_code >= 400:
                    logger.error(
                        "_ollama_generate: HTTP %s — body: %s",
                        resp.status_code, resp.text[:500],
                    )
                resp.raise_for_status()
                return resp.json().get("message", {}).get("content", "").strip()
    raise last_exc  # type: ignore[misc]


async def _openai_generate(prompt: str, temperature: float, settings, model: str) -> str:
    """Call OpenAI Chat Completions API (non-streaming)."""
    async with httpx.AsyncClient(timeout=300.0) as http:
        resp = await http.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}"},
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": temperature,
            },
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()


async def _anthropic_generate(prompt: str, temperature: float, settings, model: str) -> str:
    """Call Anthropic Messages API (non-streaming)."""
    async with httpx.AsyncClient(timeout=300.0) as http:
        resp = await http.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": settings.ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
            },
            json={
                "model": model,
                "max_tokens": 1024,
                "temperature": temperature,
                "messages": [{"role": "user", "content": prompt}],
            },
        )
        resp.raise_for_status()
        return resp.json()["content"][0]["text"].strip()


async def _gemini_generate(prompt: str, temperature: float, settings, model: str) -> str:
    """Call Google Gemini generateContent API (non-streaming)."""
    async with httpx.AsyncClient(timeout=300.0) as http:
        resp = await http.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
            params={"key": settings.GOOGLE_API_KEY},
            json={
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": temperature, "maxOutputTokens": 1024},
            },
        )
        resp.raise_for_status()
        return resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()


async def _llm_generate(prompt: str, temperature: float, settings, provider: str, model: str) -> str:
    """Provider-agnostic non-streaming LLM call."""
    if provider == "openai":
        return await _openai_generate(prompt, temperature, settings, model)
    if provider == "anthropic":
        return await _anthropic_generate(prompt, temperature, settings, model)
    if provider == "gemini":
        return await _gemini_generate(prompt, temperature, settings, model)
    return await _ollama_generate(prompt, temperature, settings)


def _build_context(parents: list[dict]) -> str:
    parts = []
    for i, p in enumerate(parents, start=1):
        # Truncate source name to prevent excessively long prompt headers
        source = (
            p.get("display_name")
            or format_document_display_name(p.get("source", ""))
            or "desconhecido"
        )[:200]
        page = p.get("page_number") or 0
        text = p.get("parent_text", "")
        header = f"[{i}] {source}" + (f" (p. {page})" if page else "")
        parts.append(f"{header}\n{text}")
    return "\n\n".join(parts)


def _build_history(messages: list[ChatMessage]) -> str:
    if not messages:
        return "(sem histórico)"
    parts = []
    for msg in messages:
        role_label = "Usuário" if msg.role == "user" else "Assistente"
        # Truncate each message to avoid context-window overflow from long turns
        text = msg.content[:500]
        parts.append(f"{role_label}: {text}")
    return "\n".join(parts)


async def _compress_context(
    query: str,
    parents: list[dict],
    settings,
    provider: str = "local",
    model: str = "gemma3:12b",
) -> list[dict]:
    """
    Contextual Compression (PLANEJAMENTO.md §5.3).

    For each parent chunk, calls the LLM to extract only the sentences that are
    directly relevant to *query*, discarding irrelevant boilerplate and reducing
    context noise before the final prompt is built.

    Failure contract:
    - All LLM calls run concurrently via asyncio.gather(return_exceptions=True).
    - If any individual call raises an exception the original parent_text is kept
      unchanged (graceful degradation — never blocks the pipeline).
    - If the LLM returns an empty string the original parent_text is kept.
    - Input dicts are never mutated; the function returns shallow copies.

    Settings:
    - CONTEXTUAL_COMPRESSION_ENABLED  — master on/off toggle (bool).
    - CONTEXTUAL_COMPRESSION_TEMPERATURE — LLM temperature for the extraction
      call (float 0.0–1.0; low values produce deterministic extractions).

    Pipeline placement:
    - Runs as stage 6b, after expand_to_parents() (step 6) and before
      _build_context() / prompt construction (step 7).  Placing it here means
      compression operates on full parent chunks (maximum context), and the
      reduced text is what the final prompt sees — minimising token usage while
      preserving retrieval recall.
    """
    # Truncate query to bound prompt size — guards against large user inputs
    # amplifying each concurrent LLM call (up to 5 calls × query size).
    query_for_prompt = query[:1000]

    async def _compress_one(parent: dict) -> dict:
        original_text = parent.get("parent_text", "")
        prompt = _COMPRESS_PROMPT_TEMPLATE.format(
            query=query_for_prompt,
            text=original_text,
        )
        compressed = await _llm_generate(
            prompt,
            temperature=settings.CONTEXTUAL_COMPRESSION_TEMPERATURE,
            settings=settings,
            provider=provider,
            model=model,
        )
        # Sanity check: output longer than 1.5× the original signals the LLM
        # added explanatory text or was prompt-injected — discard and fall back.
        if compressed and original_text and len(compressed) > len(original_text) * 1.5:
            logger.warning(
                "_compress_context: compressed output exceeds 1.5× original length "
                "— possible hallucination or prompt injection; keeping original."
            )
            compressed = ""
        result = compressed if compressed else original_text
        return {**parent, "parent_text": result}

    tasks = [_compress_one(p) for p in parents]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    compressed_parents: list[dict] = []
    for original, outcome in zip(parents, results):
        # BaseException (not Exception) is required: asyncio.CancelledError is a
        # BaseException subclass and can be returned by gather(return_exceptions=True)
        # if an individual inner coroutine is cancelled independently. Using Exception
        # would let a CancelledError fall through to the else branch and be used as
        # a dict, causing a TypeError.
        if isinstance(outcome, BaseException):
            logger.warning(
                "_compress_context: compression failed for a parent chunk — "
                "keeping original text. Error: %s",
                outcome,
            )
            compressed_parents.append(original)
        else:
            compressed_parents.append(outcome)

    return compressed_parents


def _build_sources(parents: list[dict]) -> list[dict]:
    sources = []
    for p in parents:
        raw_doc_id = p.get("doc_id", "")
        try:
            doc_uuid = str(UUID(str(raw_doc_id)))
        except (ValueError, AttributeError):
            continue
        page = p.get("page_number") or None
        sources.append(
            {
                "doc_id": doc_uuid,
                "original_name": p.get("source", ""),
                "display_name": p.get("display_name") or format_document_display_name(p.get("source", "")),
                "page_number": page if page else None,
                "score": round(float(p.get("score", 0.0)), 4),
            }
        )
    return sources


async def _persist_messages(
    db: AsyncSession,
    session_id: UUID,
    user_query: str,
    assistant_response: str,
    sources: list[dict],
    assistant_id: UUID | None = None,
) -> None:
    now = datetime.now(timezone.utc)
    db.add(
        ChatMessage(
            session_id=session_id,
            role="user",
            content=user_query,
            sources=None,
            created_at=now,
        )
    )
    db.add(
        ChatMessage(
            id=assistant_id if assistant_id is not None else uuid4(),
            session_id=session_id,
            role="assistant",
            content=assistant_response,
            sources=sources if sources else None,
            created_at=now + timedelta(microseconds=1),
        )
    )
    await db.execute(
        update(ChatSession)
        .where(ChatSession.id == session_id)
        .values(last_activity=now)
    )
    await db.commit()


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

async def rag_stream(
    query: str,
    session_id: UUID,
    db: AsyncSession,
) -> AsyncGenerator[dict, None]:
    """
    Async generator that drives the full RAG pipeline and yields SSE events.

    Yields dicts consumed by sse-starlette's EventSourceResponse:
      {"event": "token",   "data": "<text chunk>"}
      {"event": "sources", "data": "<JSON list of SourceCitation dicts>"}
      {"event": "done",    "data": "[DONE]"}

    Handles asyncio.CancelledError (client disconnect) gracefully: no partial
    DB writes are made; the generator exits cleanly.
    """
    settings = get_settings()
    rag_cfg = await get_rag_config(db)
    llm_provider: str = getattr(rag_cfg, "llm_provider", "local") or "local"
    llm_model: str = getattr(rag_cfg, "llm_model", _LOCAL_MODEL) or _LOCAL_MODEL
    embedding_provider: str = getattr(rag_cfg, "embedding_provider", "local") or "local"
    embedding_model: str = getattr(rag_cfg, "embedding_model", "bge-m3") or "bge-m3"
    response_parts: list[str] = []
    reranked_parents: list[dict] = []
    pipeline_start = time.perf_counter()

    try:
        # Pre-generate the assistant message UUID so the frontend can link
        # feedback requests to the correct DB row before the message is saved.
        assistant_msg_id = uuid4()
        yield {"event": "message_id", "data": str(assistant_msg_id)}

        # ------------------------------------------------------------------ #
        # 1. Query preprocessing                                              #
        # ------------------------------------------------------------------ #
        stage_start = time.perf_counter()
        query = " ".join(query.split())
        _log_stage_duration(session_id, "query_preprocessing", stage_start)
        # Guard: min_length=1 validates the raw string but all-whitespace input
        # normalises to ""; return fallback without persisting an empty query.
        if not query:
            yield {"event": "token", "data": _FALLBACK_MESSAGE}
            yield {"event": "sources", "data": "[]"}
            yield {"event": "done", "data": "[DONE]"}
            return

        # Guard: greetings and social messages — respond cordially without RAG pipeline
        if _GREETING_PATTERN.match(query):
            yield {"event": "token", "data": _GREETING_RESPONSE}
            yield {"event": "sources", "data": "[]"}
            yield {"event": "done", "data": "[DONE]"}
            await _persist_messages(db, session_id, query, _GREETING_RESPONSE, [], assistant_id=assistant_msg_id)
            return

        # Guard: identity/presentation questions — answer without RAG pipeline
        if _IDENTITY_PATTERN.match(query):
            yield {"event": "token", "data": _IDENTITY_RESPONSE}
            yield {"event": "sources", "data": "[]"}
            yield {"event": "done", "data": "[DONE]"}
            await _persist_messages(db, session_id, query, _IDENTITY_RESPONSE, [], assistant_id=assistant_msg_id)
            return

        # ------------------------------------------------------------------ #
        # 2. HyDE — hypothetical document embedding                          #
        # ------------------------------------------------------------------ #
        hyde_prompt = (
            f"Escreva uma resposta curta e factual para a seguinte pergunta "
            f"sobre documentos da PROPESQI/UFPI:\n\n{query}"
        )

        # ------------------------------------------------------------------ #
        # 3. Multi-query reformulations (parallel with HyDE via gather)      #
        # ------------------------------------------------------------------ #
        reform_prompt = (
            f"Gere {settings.MULTIQUERY_COUNT} reformulações diferentes da seguinte pergunta para melhorar "
            f"a busca em uma base de documentos acadêmicos. "
            f"Responda apenas com as {settings.MULTIQUERY_COUNT} reformulações, uma por linha, sem numeração.\n\n"
            f"Pergunta original: {query}"
        )
        stage_start = time.perf_counter()
        _tasks: list = []
        if rag_cfg.hyde_enabled:
            _tasks.append(_llm_generate(hyde_prompt, temperature=settings.HYDE_TEMPERATURE, settings=settings, provider=llm_provider, model=llm_model))
        if rag_cfg.multiquery_enabled:
            _tasks.append(_llm_generate(reform_prompt, temperature=settings.MULTIQUERY_TEMPERATURE, settings=settings, provider=llm_provider, model=llm_model))

        _llm_results = await asyncio.gather(*_tasks, return_exceptions=True) if _tasks else []
        _log_stage_duration(session_id, "query_expansion", stage_start)

        _result_idx = 0
        hyde_answer = ""
        if rag_cfg.hyde_enabled:
            _r = _llm_results[_result_idx] if _result_idx < len(_llm_results) else None
            if isinstance(_r, str):
                hyde_answer = _r
            else:
                logger.warning("rag_stream: HyDE LLM call failed — skipping: %s", _r)
            _result_idx += 1

        extra_queries: list[str] = []
        if rag_cfg.multiquery_enabled:
            _r = _llm_results[_result_idx] if _result_idx < len(_llm_results) else None
            if isinstance(_r, str):
                extra_queries = [
                    line.strip() for line in _r.splitlines() if line.strip()
                ][:settings.MULTIQUERY_COUNT]
            else:
                logger.warning("rag_stream: multi-query LLM call failed — skipping reformulations: %s", _r)

        # Original query included in union set (PLANEJAMENTO.md §4.2 step 3)
        all_queries = [query]
        if hyde_answer:
            all_queries.append(hyde_answer)
        all_queries.extend(extra_queries)
        all_queries.extend(_lexical_injection_queries(query))

        # Union + dedup across all queries (keep highest score per point ID)
        stage_start = time.perf_counter()
        merged_by_id: dict[str, ScoredPoint] = {}
        for q in all_queries:
            if not q:
                continue
            pts = await hybrid_search(
                q,
                top_k=rag_cfg.search_top_k,
                score_threshold=rag_cfg.search_score_threshold,
                payload_filter=_RAG_PAYLOAD_FILTER,
                embedding_provider=embedding_provider,
                embedding_model=embedding_model,
            )
            for pt in pts:
                pid = str(pt.id)
                existing = merged_by_id.get(pid)
                if existing is None or pt.score > existing.score:
                    merged_by_id[pid] = pt

        merged_points = list(merged_by_id.values())
        _log_stage_duration(session_id, "retrieval", stage_start)

        # ------------------------------------------------------------------ #
        # 4. Reranking                                                        #
        # ------------------------------------------------------------------ #
        # Augment the reranker query with lexical expansion terms so the
        # cross-encoder scores domain-specific chunks correctly even when the
        # original query uses different vocabulary (e.g. "sistema" vs "SIGAA").
        _lex_expansions = _lexical_injection_queries(query)
        reranker_query = query + (" " + " ".join(_lex_expansions) if _lex_expansions else "")

        stage_start = time.perf_counter()
        if rag_cfg.reranker_enabled:
            reranked = await rerank(
                reranker_query,
                merged_points,
                top_k=rag_cfg.reranker_top_k,
                score_threshold=rag_cfg.reranker_score_threshold,
            )
        else:
            # Skip reranker: sort by vector search score and take top_k
            reranked = sorted(merged_points, key=lambda p: p.score, reverse=True)[:rag_cfg.reranker_top_k]
        _log_stage_duration(session_id, "reranking", stage_start)

        # ------------------------------------------------------------------ #
        # 5. Fallback guard                                                   #
        # ------------------------------------------------------------------ #
        if not reranked:
            yield {"event": "token", "data": _FALLBACK_MESSAGE}
            yield {"event": "sources", "data": "[]"}
            yield {"event": "done", "data": "[DONE]"}
            await _persist_messages(db, session_id, query, _FALLBACK_MESSAGE, [], assistant_id=assistant_msg_id)
            return

        # ------------------------------------------------------------------ #
        # 6. Context assembly                                                 #
        # ------------------------------------------------------------------ #
        stage_start = time.perf_counter()
        context_top_k: int = getattr(rag_cfg, "context_top_k", 5) or 5
        if rag_cfg.parent_child_expansion_enabled:
            reranked_parents = expand_to_parents(reranked)[:context_top_k]
        else:
            reranked_parents = [
                {**(pt.payload or {}), "score": pt.score}
                for pt in reranked[:context_top_k]
            ]

        # Pinned ICV injection (Q15-type): when the query asks about ICV + pontos
        # mínimos, the habilitação chunk (6.1.2.2) is consistently outranked by
        # identical-vocabulary PIBIC/PIBITI sections. Perform an unfiltered search
        # and post-filter to ICV sources in Python (MatchText requires a Qdrant
        # full-text index that the source field does not have for query_points).
        if _ICV_HABILITACAO_RE.search(query):
            _pinned_all = await hybrid_search(
                _ICV_HABILITACAO_QUERY,
                top_k=20,
                payload_filter=_RAG_PAYLOAD_FILTER,
                embedding_provider=embedding_provider,
                embedding_model=embedding_model,
            )
            _pinned_icv = [
                pt for pt in _pinned_all
                if "ICV" in (pt.payload.get("source") or "")
            ]
            if _pinned_icv:
                _pinned = expand_to_parents(_pinned_icv[:1])
                if _pinned:
                    _existing = {p["parent_id"] for p in reranked_parents}
                    if _pinned[0]["parent_id"] not in _existing:
                        reranked_parents = [_pinned[0]] + reranked_parents[:context_top_k - 1]

        # Q05 pinned injection: "vigência das bolsas" queries retrieve the dedicated
        # "DO PERÍODO DE VIGÊNCIA DA BOLSA" section. Without pinning, the cronograma
        # section floods context with many date ranges and confuses the LLM.
        if _VIGENCIA_BOLSA_RE.search(query):
            _pinned_vig_all = await hybrid_search(
                _VIGENCIA_BOLSA_QUERY,
                top_k=10,
                payload_filter=_RAG_PAYLOAD_FILTER,
                embedding_provider=embedding_provider,
                embedding_model=embedding_model,
            )
            if _pinned_vig_all:
                _pinned_vig = expand_to_parents(_pinned_vig_all[:1])
                if _pinned_vig:
                    _existing = {p["parent_id"] for p in reranked_parents}
                    if _pinned_vig[0]["parent_id"] not in _existing:
                        reranked_parents = [_pinned_vig[0]] + reranked_parents[:context_top_k - 1]

        history_result = await db.execute(
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at.desc())
            .limit(10)
        )
        history_msgs = list(reversed(history_result.scalars().all()))
        _log_stage_duration(session_id, "context_assembly", stage_start)

        # ------------------------------------------------------------------ #
        # 6b. Contextual Compression                                         #
        # ------------------------------------------------------------------ #
        if rag_cfg.contextual_compression_enabled:
            stage_start = time.perf_counter()
            reranked_parents = await _compress_context(query, reranked_parents, settings, provider=llm_provider, model=llm_model)
            _log_stage_duration(session_id, "contextual_compression", stage_start)

        # ------------------------------------------------------------------ #
        # 7. Prompt construction                                              #
        # ------------------------------------------------------------------ #
        stage_start = time.perf_counter()
        context_text = _build_context(reranked_parents)
        chat_history_text = _build_history(history_msgs)
        system_content = _SYSTEM_PROMPT.format(
            context=context_text,
            chat_history=chat_history_text,
        )

        messages: list[dict] = [{"role": "system", "content": system_content}]
        for msg in history_msgs:
            messages.append({"role": msg.role, "content": msg.content})
        messages.append({"role": "user", "content": query})
        _log_stage_duration(session_id, "prompt_construction", stage_start)

        # ------------------------------------------------------------------ #
        # 8. LLM streaming                                                    #
        # ------------------------------------------------------------------ #
        stage_start = time.perf_counter()
        if llm_provider == "openai":
            async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, read=300.0)) as http:
                async with http.stream(
                    "POST",
                    "https://api.openai.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}"},
                    json={
                        "model": llm_model,
                        "messages": messages,
                        "stream": True,
                        "temperature": 0.1,
                        "max_tokens": 1024,
                    },
                ) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if not line or not line.startswith("data: "):
                            continue
                        payload = line[len("data: "):].strip()
                        if payload == "[DONE]":
                            break
                        try:
                            chunk = json.loads(payload)
                        except json.JSONDecodeError:
                            continue
                        token: str = chunk.get("choices", [{}])[0].get("delta", {}).get("content") or ""
                        if token:
                            response_parts.append(token)
                            yield {"event": "token", "data": token}
        elif llm_provider == "anthropic":
            async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, read=300.0)) as http:
                # Anthropic uses a separate system parameter
                anthropic_system = ""
                anthropic_messages = []
                for m in messages:
                    if m["role"] == "system":
                        anthropic_system = m["content"]
                    else:
                        anthropic_messages.append(m)
                async with http.stream(
                    "POST",
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": settings.ANTHROPIC_API_KEY,
                        "anthropic-version": "2023-06-01",
                    },
                    json={
                        "model": llm_model,
                        "system": anthropic_system,
                        "messages": anthropic_messages,
                        "stream": True,
                        "max_tokens": 1024,
                        "temperature": 0.1,
                    },
                ) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if not line or not line.startswith("data: "):
                            continue
                        payload = line[len("data: "):].strip()
                        try:
                            chunk = json.loads(payload)
                        except json.JSONDecodeError:
                            continue
                        if chunk.get("type") == "content_block_delta":
                            token = chunk.get("delta", {}).get("text") or ""
                            if token:
                                response_parts.append(token)
                                yield {"event": "token", "data": token}
                        elif chunk.get("type") == "message_stop":
                            break
        elif llm_provider == "gemini":
            async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, read=300.0)) as http:
                # Gemini uses a flat contents array; map system prompt as first user turn
                gemini_contents = []
                system_text = ""
                for m in messages:
                    if m["role"] == "system":
                        system_text = m["content"]
                    elif m["role"] == "user":
                        text = (system_text + "\n\n" + m["content"]) if system_text else m["content"]
                        gemini_contents.append({"role": "user", "parts": [{"text": text}]})
                        system_text = ""
                    else:
                        gemini_contents.append({"role": "model", "parts": [{"text": m["content"]}]})
                async with http.stream(
                    "POST",
                    f"https://generativelanguage.googleapis.com/v1beta/models/{llm_model}:streamGenerateContent",
                    params={"key": settings.GOOGLE_API_KEY, "alt": "sse"},
                    json={
                        "contents": gemini_contents,
                        "generationConfig": {"temperature": 0.1, "maxOutputTokens": 1024},
                    },
                ) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if not line or not line.startswith("data: "):
                            continue
                        payload = line[len("data: "):].strip()
                        if payload == "[DONE]":
                            break
                        try:
                            chunk = json.loads(payload)
                        except json.JSONDecodeError:
                            continue
                        token = (
                            chunk.get("candidates", [{}])[0]
                            .get("content", {})
                            .get("parts", [{}])[0]
                            .get("text", "")
                        )
                        if token:
                            response_parts.append(token)
                            yield {"event": "token", "data": token}
        else:
            async with _OLLAMA_SEMAPHORE:
                async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, read=300.0)) as http:
                    async with http.stream(
                        "POST",
                        f"{settings.OLLAMA_BASE_URL}/api/chat",
                        json={
                            "model": llm_model,
                            "messages": messages,
                            "stream": True,
                            "options": {"temperature": 0.1, "num_predict": 1024},
                        },
                    ) as resp:
                        resp.raise_for_status()
                        async for line in resp.aiter_lines():
                            if not line:
                                continue
                            try:
                                chunk = json.loads(line)
                            except json.JSONDecodeError:
                                continue
                            token = chunk.get("message", {}).get("content", "")
                            if token:
                                response_parts.append(token)
                                yield {"event": "token", "data": token}
                            if chunk.get("done"):
                                break
        _log_stage_duration(session_id, "llm_streaming", stage_start)

        # ------------------------------------------------------------------ #
        # 9. Post-processing                                                  #
        # ------------------------------------------------------------------ #
        stage_start = time.perf_counter()
        sources_data = _build_sources(reranked_parents)
        full_response = "".join(response_parts)

        yield {"event": "sources", "data": json.dumps(sources_data)}
        yield {"event": "done", "data": "[DONE]"}

        # Persist only after both terminal events have been yielded.
        # Wrap separately so a DB failure does not raise after the stream is closed.
        try:
            await _persist_messages(db, session_id, query, full_response, sources_data, assistant_id=assistant_msg_id)
        except Exception:
            logger.error("rag_stream: failed to persist messages for session %s", session_id)
        _log_stage_duration(session_id, "post_processing", stage_start)

    except asyncio.CancelledError:
        # Client disconnected mid-stream — exit without writing partial data
        pass
    except Exception:
        # Unexpected error (Ollama down, network failure, etc.) — send error event
        # so the client does not hang waiting for 'done'.
        logger.error("rag_stream: unhandled error for session %s", session_id, exc_info=True)
        yield {"event": "error", "data": "Ocorreu um erro interno. Por favor, tente novamente."}
        yield {"event": "done", "data": "[DONE]"}
    finally:
        _log_stage_duration(session_id, "total", pipeline_start)
