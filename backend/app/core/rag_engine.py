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
from qdrant_client.models import FieldCondition, Filter, MatchAny, MatchText, MatchValue, ScoredPoint

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

# Inverse of _RAG_PAYLOAD_FILTER — used only as a rescue pass (see the
# fallback guard in rag_stream) when the primary, edital-scoped search finds
# nothing at all. Many questions about portarias/relatórios anuais have no
# lexical signal ("Qual é a função da CBIO?"), so a regex-guarded special
# case (the pattern used elsewhere in this file) can't reliably catch them —
# gating on "the primary search returned nothing" instead means the rescue
# never competes with a successful edital retrieval and can't reintroduce
# the exact regression _RAG_PAYLOAD_FILTER was added to prevent.
_PORTARIA_RELATORIO_FILTER = Filter(
    must=[
        FieldCondition(
            key="doc_type",
            match=MatchAny(any=["portaria", "relatorio"]),
        )
    ]
)

# Matches an explicit cycle mention like "2025/2026" or "2025-2026" in the
# user's own query.
_CYCLE_IN_QUERY_RE = re.compile(r"\b(20\d{2})[/-](20\d{2})\b")


def _effective_cycle(query: str) -> str | None:
    """Derive the active cycle strictly from an explicit mention in the
    question itself (e.g. "...para 2025/2026?").

    Deliberately NOT falling back to rag_config.active_edital_cycle for
    cycle-agnostic questions: a single global "current cycle" can't be
    enforced as a blanket default when not every program has been reissued
    for it yet (e.g. ICV has no 2026/2027 edition) — unconditionally
    preferring the configured cycle would silently empty the candidate pool
    for those programs instead of falling back to their only (older) edital.
    """
    match = _CYCLE_IN_QUERY_RE.search(query)
    return f"{match.group(1)}/{match.group(2)}" if match else None


def _cycle_survivors(points: list, cycle: str | None) -> list:
    """Presence-gated cycle guard: excludes chunks tagged with a DIFFERENT
    cycle than `cycle`, but only when at least one candidate is actually
    tagged with `cycle` — a hard, unconditional exclusion would silently wipe
    out the only available source for a program that hasn't published an
    edital for the configured cycle yet (e.g. ICV has no 2026/2027 edition:
    filtering its 2025/2026 chunks whenever active_edital_cycle=2026/2027
    leaves nothing at all, converting a working answer into a fallback).
    Chunks with no edital_cycle tag are always eligible, regardless."""
    if not cycle:
        return points
    same_cycle = [pt for pt in points if (pt.payload or {}).get("edital_cycle") == cycle]
    if not same_cycle:
        return points
    return [pt for pt in points if (pt.payload or {}).get("edital_cycle") in (None, cycle)]

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

# Q06 pinned injection: PIBIC (not PIBIC-EM/PIBITI/ICV) habilitação pontos
# mínimos. PIBIC-EM and PIBITI share near-identical vocabulary with regular
# PIBIC ("plano de trabalho", "produção intelectual", "pontos mínimos"), and
# that generic phrasing consistently outranks PIBIC's own specific "10 (dez)
# pontos" clause (buried mid-paragraph, competing against denser generic
# content from other programs). text_contains anchors to PIBIC's literal
# threshold, which naturally excludes PIBIC-EM's clause (a different number,
# "5 (cinco) pontos") without needing negative source filtering.
_PIBIC_HABILITACAO_RE = re.compile(
    r"\bPIBIC\b.{0,120}\bpontos?\s+m[íi]nimos?\b"
    r"|\bpontos?\s+m[íi]nimos?\b.{0,120}\bPIBIC\b",
    re.IGNORECASE,
)
_PIBIC_EM_PIBITI_ICV_RE = re.compile(r"PIBIC-EM|PIBITI|\bICV\b", re.IGNORECASE)
_PIBIC_HABILITACAO_QUERY = (
    "PIBIC habilitado etapa análise planos trabalho proponente atingir "
    "mínimo 10 dez pontos somatório total tabela pontuação produção "
    "intelectual Iniciação Científica"
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

# Q25 pinned injection: when query asks about vigência of ALL programs simultaneously,
# inject the vigência section from each non-PIBIC edital explicitly.
# PIBIC vigência is already covered by _VIGENCIA_BOLSA_RE above; without this,
# only the PIBIC chunk survives context_top_k and the LLM omits ICV, PIBITI, PIBIC-EM.
_TODOS_PROGRAMAS_VIGENCIA_RE = re.compile(
    r"\bvig[eê]ncia\b.{0,80}\b(todos|todas)\b"
    r"|\b(todos|todas)\b.{0,80}\bvig[eê]ncia\b",
    re.IGNORECASE,
)
_VIGENCIA_MULTI_EDITAL: list[tuple[str, list[str]]] = [
    (
        "DO PERÍODO DE VIGÊNCIA DA BOLSA vigência doze meses início término setembro agosto ICV Iniciação Científica Voluntária",
        ["icv"],
    ),
    (
        "DO PERÍODO DE VIGÊNCIA DA BOLSA vigência doze meses início término setembro agosto PIBITI Inovação Tecnológica",
        ["pibiti"],
    ),
    (
        "DO PERÍODO DE VIGÊNCIA DA BOLSA vigência doze meses início término setembro agosto PIBICEM PIBIC-EM Ensino Médio",
        ["pibicem", "pibic-em"],
    ),
]

# Q18 pinned injection: PIBITI acúmulo de bolsas — a cláusula de devolução de valores
# (4.2.7 ou similar) fica abaixo do top-k por ter vocabulário diferente da query sobre
# "acumular bolsas". A query usa "acumular/empregos" mas a cláusula usa
# "devolver/mensalidades/indevidamente".
_PIBITI_ACUMULO_RE = re.compile(
    r"\b(acumul|PIBITI).{0,60}\b(bolsa|emprego|est[aá]gio|outr)\b"
    r"|\b(bolsa|emprego|est[aá]gio).{0,60}\b(acumul|PIBITI)\b",
    re.IGNORECASE,
)
_PIBITI_ACUMULO_QUERY = (
    "PIBITI vedado acumular bolsa estágio remunerado extracurricular devolver devolution "
    "mensalidades recebidas indevidamente CNPq UFPI valores atualizados 4.2"
)

# Q14 pinned injection: ICV relatório parcial — the Aditivo nº 2 shifts the submission
# deadline to 17–31 March 2026. The dates are retrieved correctly (score 3.5 since Passo 2)
# but the source attribution is wrong: the LLM cites generic edital docs instead of
# "Aditivo nº 2 ICV". Pinning the aditivo chunk to context position [1] and adding Rule 7
# to the system prompt should fix both the source citation and the SIGAA omission.
_ICV_RELATORIO_PARCIAL_RE = re.compile(
    r"\brelatório\s+parcial\b.{0,80}\bICV\b|\bICV\b.{0,80}\brelatório\s+parcial\b"
    r"|\bprazo\b.{0,80}\brelatório\b.{0,80}\bICV\b|\bICV\b.{0,80}\bprazo\b.{0,60}\brelatório\b",
    re.IGNORECASE,
)
_ICV_ADITIVO_RELATORIO_QUERY = (
    "17 31 março 2026 relatório parcial prazo envio SIGAA exclusivamente "
    "ICV Aditivo nº 2 cronograma Iniciação Científica Voluntária"
)

# Q21 pinned injection: PIBICEM seção 3.2.1 — bolsista não precisa ser do mesmo colégio.
# The query uses "mesmo colégio" but the clause uses "lotado"/"obrigatoriedade"/"vinculado",
# causing a vocabulary mismatch that drops the correct chunk below the reranker threshold.
_PIBICEM_COLEGIO_RE = re.compile(
    r"\b(col[eé]gio|escola)\b.{0,100}\b(orientador|mesmo|PIBICEM|PIBIC.EM|ensino\s+m[eé]dio)\b"
    r"|\b(orientador|mesmo|PIBICEM|PIBIC.EM)\b.{0,100}\b(col[eé]gio|escola)\b",
    re.IGNORECASE,
)
_PIBICEM_COLEGIO_QUERY = (
    "PIBIC-EM PIBICEM bolsista discente matriculado Ensino Médio concomitante Técnico "
    "sem obrigatoriedade vinculado colégio escola lotado orientador 3.2.1 requisito"
)

# Q03/Q10 pinned injection: PIBIC "3.3 Discente" eligibility section — the IRA clause
# (Q03) and the PIBIC-Af affirmative-action clause (Q10) live in the same parent chunk
# (page 2 of the main edital), but generic retrieval surfaces "orientador"/"cota de
# bolsas" sections from the same document instead of this one.
_PIBIC_DISCENTE_RE = re.compile(r"\bIRA\b(?!.*PIBIC-EM)|\bPIBIC-?Af\b", re.IGNORECASE)
_PIBIC_DISCENTE_QUERY = (
    "Índice de Rendimento Acadêmico IRA mínimo recomendado igual superior 7,0 sete "
    "ação afirmativa Lei de Cotas 12.711/2012 PIBIC-Af discente bolsista graduação "
    "matrícula período compatível vigência"
)

# Q19 pinned injection: PIBITI 4.1.5.1 — orientador deve orientar o bolsista
# diretamente nas distintas fases da pesquisa; the Anexo I scoring clause ("...como
# coorientador") shares the word "coorientador" and wins the generic search instead.
_PIBITI_COORIENTADOR_RE = re.compile(r"\bcoorientador\b", re.IGNORECASE)
_PIBITI_ORIENTACAO_QUERY = (
    "PIBITI orientador cumprir requisitos orientar bolsista discente voluntário "
    "distintas fases pesquisa tecnológica diretamente 4.1.5"
)

# Q24 pinned injection: ICV vs PIBIC "natureza da participação" — no single chunk
# states the voluntary/paid distinction explicitly; the section TITLES carry the
# signal ("vigência da BOLSA" no PIBIC vs "vigência da PARTICIPAÇÃO VOLUNTÁRIA" no
# ICV). Pin both side by side so the LLM can contrast them.
_ICV_PIBIC_NATUREZA_RE = re.compile(
    r"\bdiferen[cç]a\b.{0,60}\bICV\b.{0,60}\bPIBIC\b"
    r"|\bdiferen[cç]a\b.{0,60}\bPIBIC\b.{0,60}\bICV\b"
    r"|\bnatureza\b.{0,100}\bICV\b.{0,60}\bPIBIC\b"
    r"|\bnatureza\b.{0,100}\bPIBIC\b.{0,60}\bICV\b",
    re.IGNORECASE,
)
_ICV_VOLUNTARIA_QUERY = (
    "DO PERÍODO DE VIGÊNCIA DA PARTICIPAÇÃO VOLUNTÁRIA ICV discente voluntário sem bolsa"
)
_PIBIC_BOLSA_QUERY = (
    "DO PERÍODO DE VIGÊNCIA DA BOLSA PIBIC bolsista CNPq UFPI vigência doze meses"
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
    # Q14-type: "relatório parcial" + "ICV" → Aditivo nº 2 vocabulary + SIGAA
    # The Aditivo shifts the deadline; without this injection the lexical match
    # for "SIGAA" and "Aditivo nº 2" is weak relative to generic edital chunks.
    (
        re.compile(
            r"\brelatório\s+parcial\b.{0,80}\bICV\b|\bICV\b.{0,80}\brelatório\s+parcial\b"
            r"|\bprazo\b.{0,60}\brelatório\b.{0,60}\bICV\b",
            re.IGNORECASE,
        ),
        "ICV relatório parcial prazo envio SIGAA exclusivamente Aditivo nº 2 março 2026 "
        "17 31 cronograma Iniciação Científica Voluntária sistema integrado",
    ),
    # Q21-type: "colégio"/"escola" → PIBICEM 3.2.1 vocabulary (mismatch: query says
    # "mesmo colégio/escola" but the clause uses "lotado", "obrigatoriedade", "vinculado")
    (
        re.compile(r"\b(col[eé]gio|escola)\b", re.IGNORECASE),
        "sem obrigatoriedade vinculado colégio escola lotado discente matriculado "
        "PIBIC-EM PIBICEM Ensino Médio concomitante Técnico orientador 3.2.1",
    ),
    # Q18-type: "acumular bolsas"/"PIBITI" → devolução clause (mismatch: query uses
    # "acumular/empregos" but the penalty clause uses "devolver/mensalidades/indevidamente")
    (
        re.compile(
            r"\b(acumul|PIBITI).{0,60}\b(bolsa|emprego|est[aá]gio|outr)\b"
            r"|\b(bolsa|emprego|est[aá]gio).{0,60}\b(acumul|PIBITI)\b",
            re.IGNORECASE,
        ),
        "PIBITI vedado acumular bolsa estágio remunerado extracurricular devolver "
        "mensalidades recebidas indevidamente CNPq UFPI valores atualizados",
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
    # Q03-type: "IRA" for the main PIBIC edital (not PIBIC-EM, which has its own IRA
    # clause and its own query — negative lookahead keeps this from firing on Q22).
    (
        re.compile(r"\bIRA\b(?!.*PIBIC-EM)", re.IGNORECASE),
        "Índice de Rendimento Acadêmico IRA mínimo recomendado igual superior 7,0 sete "
        "bolsista graduação matrícula período compatível vigência PIBIC PIBIC-Af",
    ),
    # Q10-type: "PIBIC-Af" eligibility — the affirmative-action clause (Lei de Cotas)
    # is crowded out by the more generic orientador/obrigações sections of the same doc.
    (
        re.compile(r"\bPIBIC-?Af\b", re.IGNORECASE),
        "ação afirmativa Lei de Cotas 12.711/2012 ingresso UFPI PIBIC-Af beneficiário "
        "discente matriculado graduação IRA elegibilidade requisitos",
    ),
    # Q16-type: "foco"/"objetivo" + PIBITI — the Seção 2 objectives paragraph is
    # crowded out by cover-page/header boilerplate that also matches "PIBITI".
    (
        re.compile(
            r"\b(foco|objetivo)\b.{0,80}\bPIBITI\b|\bPIBITI\b.{0,80}\b(foco|objetivo)\b",
            re.IGNORECASE,
        ),
        "PIBITI pesquisa aplicada desenvolvimento tecnológico inovação inserção recursos "
        "humanos formação capacidade inovadora empresas cidadão criativo empreendedor "
        "metodologias pesquisa tecnológica produtos tecnológicos",
    ),
    # Q19-type: "coorientador" — the PIBITI clause vedando coorientador is crowded out
    # by unrelated Anexo/ad-hoc boilerplate that also mentions "orientador".
    (
        re.compile(r"\bcoorientador\b", re.IGNORECASE),
        "PIBITI vedada inclusão coorientador orientador orienta diretamente distintas "
        "fases pesquisa tecnológica",
    ),
    # Q24-type: ICV vs PIBIC "diferença"/"natureza" of participation — the voluntary
    # (ICV) vs remunerated (PIBIC) distinction isn't stated verbatim in any single
    # crowded-out chunk; inject vocabulary from both sides explicitly.
    (
        re.compile(
            r"\bdiferen[cç]a\b.{0,60}\bICV\b.{0,60}\bPIBIC\b"
            r"|\bdiferen[cç]a\b.{0,60}\bPIBIC\b.{0,60}\bICV\b"
            r"|\bnatureza\b.{0,100}\bICV\b.{0,60}\bPIBIC\b"
            r"|\bnatureza\b.{0,100}\bPIBIC\b.{0,60}\bICV\b",
            re.IGNORECASE,
        ),
        "ICV caráter voluntário participação sem bolsa remunerada PIBIC bolsa remunerada "
        "CNPq UFPI Termo de Compromisso plano de trabalho relatórios Seminário Iniciação "
        "Científica diferença natureza",
    ),
]


def _lexical_injection_queries(query: str) -> list[str]:
    """Return synthetic queries for patterns that suffer from lexical mismatch."""
    return [expansion for pattern, expansion in _LEXICAL_EXPANSIONS if pattern.search(query)]


async def _pinned_search(
    query_text: str,
    *,
    top_k: int,
    payload_filter: Filter,
    embedding_provider: str,
    embedding_model: str,
    source_contains: list[str] | None = None,
    doc_type: str | None = None,
    page_number: int | None = None,
    text_contains: list[str] | None = None,
    cycle_filter: str | None = None,
) -> list[dict]:
    """Shared implementation for the pinned-injection pattern used throughout
    rag_stream(): search with a hand-tuned query, post-filter the raw Qdrant
    points in Python (Qdrant's query_points has no full-text index on these
    payload fields), then expand the surviving points to parent context.

    cycle_filter restricts results to chunks tagged with a matching
    edital_cycle payload value; chunks with no edital_cycle set (the entire
    corpus prior to this feature) remain eligible regardless of cycle_filter.
    """
    points = await hybrid_search(
        query_text,
        top_k=top_k,
        payload_filter=payload_filter,
        embedding_provider=embedding_provider,
        embedding_model=embedding_model,
    )

    def _matches(pt) -> bool:
        payload = pt.payload or {}
        if source_contains and not any(
            k.lower() in (payload.get("source") or "").lower() for k in source_contains
        ):
            return False
        if doc_type and (payload.get("doc_type") or "") != doc_type:
            return False
        if page_number is not None and (payload.get("page_number") or 0) != page_number:
            return False
        if text_contains and not all(
            k.lower() in (payload.get("parent_text") or payload.get("text_preview") or "").lower()
            for k in text_contains
        ):
            return False
        return True

    candidates = [pt for pt in points if _matches(pt)]
    # Cycle guard applied last, and only among candidates that already match
    # every other criterion — see _cycle_survivors for why this is
    # presence-gated rather than an unconditional exclusion.
    candidates = _cycle_survivors(candidates, cycle_filter)
    return expand_to_parents(candidates)


def _promote_pinned(reranked_parents: list[dict], pinned: dict, context_top_k: int) -> list[dict]:
    """Force `pinned` into context position [0], deduplicating any existing
    occurrence of the same parent elsewhere in the list first.

    Earlier versions skipped promotion entirely whenever the pinned parent
    was already present anywhere in reranked_parents — the assumption being
    "already there" meant "no work to do". That assumption breaks when the
    main retrieval surfaces the right chunk but buries it near the bottom of
    context_top_k: the chunk is technically in the prompt, but the LLM
    reliably fails to use it from a low position. A change to chunk
    embeddings (e.g. child-chunk overlap) is enough to shift a pinned target
    from "absent" to "present but buried", silently regressing a question
    that used to pass. Always promoting — never just skipping — removes that
    failure mode for good.
    """
    pid = pinned["parent_id"]
    return [pinned] + [p for p in reranked_parents if p["parent_id"] != pid][: context_top_k - 1]


async def _union_search(
    queries: list[str],
    *,
    payload_filter: Filter,
    rag_cfg,
    embedding_provider: str,
    embedding_model: str,
) -> list[ScoredPoint]:
    """Union+dedup hybrid_search across `queries`, keeping the max RRF score
    per point id. Extracted so the primary (edital-scoped) search and the
    portaria/relatorio pool (see rag_stream) share one implementation."""
    merged_by_id: dict[str, ScoredPoint] = {}
    for q in queries:
        if not q:
            continue
        pts = await hybrid_search(
            q,
            top_k=rag_cfg.search_top_k,
            score_threshold=rag_cfg.search_score_threshold,
            payload_filter=payload_filter,
            embedding_provider=embedding_provider,
            embedding_model=embedding_model,
        )
        for pt in pts:
            pid = str(pt.id)
            existing = merged_by_id.get(pid)
            if existing is None or pt.score > existing.score:
                merged_by_id[pid] = pt
    return list(merged_by_id.values())


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
6. Ao descrever vigência de bolsas, mencione sempre a duração em meses \
(ex: "12 meses" ou "doze meses"), a data de início e a data de término.
7. Se o contexto incluir trechos identificados como "ADITIVO: ..." (ex: "ADITIVO: Aditivo nº 2"), \
cite explicitamente esse aditivo ao mencionar os dados por ele alterados. \
Modelo: "Conforme o Aditivo nº 2 do Edital ICV 2025/2026, o prazo passou a ser...". \
Se o contexto indicar que o envio de relatórios nos editais de iniciação científica é feito \
"exclusivamente pelo sistema SIGAA" (ou "exclusivamente via SIGAA"), inclua essa informação \
ao descrever prazos de envio de qualquer relatório (parcial, semestral ou final).
8. Não use frases de preenchimento como "este documento fala sobre...", "de acordo com o \
documento em minha base de dados..." ou "com base no contexto apresentado...". Vá direto ao conteúdo da resposta.

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


def _format_aditivo_name(source: str) -> str:
    """Derive a human-readable label from an aditivo filename.

    PDF title metadata for aditivos often repeats the parent edital's title
    ("EDITAL - Iniciação Científica...") rather than identifying the aditivo
    number, so display_name from the payload is unreliable for these documents.
    The filename is always authoritative: Aditivo_2_-_ICV_2025-2026_... .pdf
    → "Aditivo nº 2 – ICV 2025/2026".
    """
    m = re.match(r"Aditivo_(\d+)_-_(.+?)_\d{4}-\d{4}", source, re.IGNORECASE)
    if m:
        num, prog = m.group(1), m.group(2)
        return f"Aditivo nº {num} – {prog} 2025/2026"
    return ""


def _build_context(parents: list[dict]) -> str:
    parts = []
    for i, p in enumerate(parents, start=1):
        # For aditivos, PDF title metadata often mirrors the parent edital title
        # ("EDITAL - Iniciação Científica...") — use the filename instead so the
        # LLM sees "Aditivo nº 2 – ICV 2025/2026" in the context header and can
        # cite it correctly (Rule 7).
        if p.get("doc_type") == "aditivo":
            aditivo_label = _format_aditivo_name(p.get("source", ""))
            source = aditivo_label or (
                p.get("display_name")
                or format_document_display_name(p.get("source", ""))
                or "desconhecido"
            )
        else:
            aditivo_label = ""
            source = (
                p.get("display_name")
                or format_document_display_name(p.get("source", ""))
                or "desconhecido"
            )
        source = source[:200]
        page = p.get("page_number") or 0
        text = p.get("parent_text", "")
        # Any aditivo reaching the context — via normal reranking or via a
        # pinned injection — gets the same "ADITIVO: <label>" prefix so
        # Rule 7 of _SYSTEM_PROMPT triggers, instead of a per-question hack.
        if aditivo_label and not text.startswith("ADITIVO"):
            text = f"ADITIVO: {aditivo_label}\n{text}"
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
        if p.get("doc_type") == "aditivo":
            display_name = _format_aditivo_name(p.get("source", "")) or p.get("display_name") or format_document_display_name(p.get("source", ""))
        else:
            display_name = p.get("display_name") or format_document_display_name(p.get("source", ""))
        sources.append(
            {
                "doc_id": doc_uuid,
                "original_name": p.get("source", ""),
                "display_name": display_name,
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
    active_cycle: str | None = _effective_cycle(query)
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

        # Augment the reranker query with lexical expansion terms so the
        # cross-encoder scores domain-specific chunks correctly even when the
        # original query uses different vocabulary (e.g. "sistema" vs "SIGAA").
        # Computed up front since it only depends on `query`, not on retrieval
        # results — needed by both the primary search and the rescue pass below.
        _lex_expansions = _lexical_injection_queries(query)
        reranker_query = query + (" " + " ".join(_lex_expansions) if _lex_expansions else "")

        # ------------------------------------------------------------------ #
        # 3b. Retrieval                                                        #
        # ------------------------------------------------------------------ #
        # _RAG_PAYLOAD_FILTER protects edital questions from a documented
        # regression (Passo 5, relatorio_otimizacao_rag.md — portarias naming
        # programs by name used to outrank the real edital content in the
        # cross-encoder reranker). But some questions only have an answer in
        # portaria/relatorio docs, most with no lexical signal to gate a regex
        # on ("Qual é a função da CBIO?").
        stage_start = time.perf_counter()
        primary_points = await _union_search(
            all_queries, payload_filter=_RAG_PAYLOAD_FILTER, rag_cfg=rag_cfg,
            embedding_provider=embedding_provider, embedding_model=embedding_model,
        )
        _log_stage_duration(session_id, "retrieval", stage_start)

        # ------------------------------------------------------------------ #
        # 4. Reranking (with portaria/relatorio rescue)                       #
        # ------------------------------------------------------------------ #
        stage_start = time.perf_counter()
        primary_points = _cycle_survivors(primary_points, active_cycle)

        if rag_cfg.reranker_enabled:
            # Routing between the edital pool and the portaria/relatorio pool
            # needs a score that's comparable ACROSS two independent search
            # calls. Raw hybrid_search (RRF) scores are NOT that: they're a
            # rank-position artifact local to each call's own small top-k
            # list (empirically verified — many plain edital questions from
            # the original 30-question golden set score just as high, or
            # higher, on the portaria/relatorio pool as genuine portaria
            # questions do, with no threshold separating the two). The
            # cross-encoder reranker's sigmoid-normalized score IS a
            # calibrated, comparable relevance estimate for a given
            # (query, chunk) pair regardless of which pool the chunk came
            # from — so only attempt the rescue when a real reranker is
            # available to arbitrate between the two pools.
            rescue_points = await _union_search(
                all_queries, payload_filter=_PORTARIA_RELATORIO_FILTER, rag_cfg=rag_cfg,
                embedding_provider=embedding_provider, embedding_model=embedding_model,
            )
            rescue_points = _cycle_survivors(rescue_points, active_cycle)
            primary_reranked, rescue_reranked = await asyncio.gather(
                rerank(reranker_query, primary_points, top_k=rag_cfg.reranker_top_k, score_threshold=rag_cfg.reranker_score_threshold),
                rerank(reranker_query, rescue_points, top_k=rag_cfg.reranker_top_k, score_threshold=rag_cfg.reranker_score_threshold),
            )
            primary_top = max((p.score for p in primary_reranked), default=0.0)
            rescue_top = max((p.score for p in rescue_reranked), default=0.0)
            reranked = rescue_reranked if rescue_top > primary_top else primary_reranked
        else:
            # No cross-encoder available to arbitrate — without one, a
            # rescue attempt has no reliable signal (see above) and risks
            # exactly the Passo 5 regression _RAG_PAYLOAD_FILTER exists to
            # prevent. Fall back to the original, safe edital-only behavior;
            # the rescue activates automatically once the reranker is
            # reactivated (already the next step in the ongoing gradual
            # reactivation cycle — relatorio_otimizacao_rag.md).
            reranked = sorted(primary_points, key=lambda p: p.score, reverse=True)[:rag_cfg.reranker_top_k]
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
            # Raw Qdrant payloads never carry a "parent_id" key (it's a
            # chunker-internal field, not copied into payload at indexing
            # time — see app/ingestion/chunker.py). expand_to_parents()
            # papers over this with `payload.get("parent_id") or str(point.id)`;
            # mirror that fallback here so the pinned-injection blocks below
            # (which all do direct `p["parent_id"]` access) don't KeyError
            # when parent_child_expansion_enabled is False.
            reranked_parents = [
                {
                    **(pt.payload or {}),
                    "parent_id": (pt.payload or {}).get("parent_id") or str(pt.id),
                    "score": pt.score,
                }
                for pt in reranked[:context_top_k]
            ]

        # Pinned ICV injection (Q15-type): when the query asks about ICV + pontos
        # mínimos, the habilitação chunk (6.1.2.2) is consistently outranked by
        # identical-vocabulary PIBIC/PIBITI sections. page_number==4 pins the
        # exact chunk with "6.1.2.2 ... 5 (cinco) pontos" — without it, the
        # highest-ranked ICV hit is often page 2 (eligibility criteria, no
        # point threshold), which still lacks the answer.
        if _ICV_HABILITACAO_RE.search(query):
            _pinned = await _pinned_search(
                _ICV_HABILITACAO_QUERY,
                top_k=20,
                payload_filter=_RAG_PAYLOAD_FILTER,
                embedding_provider=embedding_provider,
                embedding_model=embedding_model,
                source_contains=["icv"],
                page_number=4,
                cycle_filter=active_cycle,
            )
            if _pinned:
                reranked_parents = _promote_pinned(reranked_parents, _pinned[0], context_top_k)

        # Pinned PIBIC injection (Q06-type): same failure mode as the ICV block
        # above — the "10 (dez) pontos" habilitação clause loses the reranker
        # to PIBIC-EM/PIBITI sections sharing the same generic vocabulary.
        # Guarded so it never fires for questions explicitly about a different
        # program (PIBIC-EM/PIBITI/ICV), which have their own pinned blocks.
        if _PIBIC_HABILITACAO_RE.search(query) and not _PIBIC_EM_PIBITI_ICV_RE.search(query):
            _pinned_pibic = await _pinned_search(
                _PIBIC_HABILITACAO_QUERY,
                top_k=20,
                payload_filter=_RAG_PAYLOAD_FILTER,
                embedding_provider=embedding_provider,
                embedding_model=embedding_model,
                source_contains=["pibic"],
                text_contains=["10 (dez) pontos"],
                cycle_filter=active_cycle,
            )
            if _pinned_pibic:
                reranked_parents = _promote_pinned(reranked_parents, _pinned_pibic[0], context_top_k)

        # Q05 pinned injection: "vigência das bolsas" queries retrieve the dedicated
        # "DO PERÍODO DE VIGÊNCIA DA BOLSA" section. Without pinning, the cronograma
        # section floods context with many date ranges and confuses the LLM.
        if _VIGENCIA_BOLSA_RE.search(query):
            _pinned_vig = await _pinned_search(
                _VIGENCIA_BOLSA_QUERY,
                top_k=10,
                payload_filter=_RAG_PAYLOAD_FILTER,
                embedding_provider=embedding_provider,
                embedding_model=embedding_model,
                cycle_filter=active_cycle,
            )
            if _pinned_vig:
                reranked_parents = _promote_pinned(reranked_parents, _pinned_vig[0], context_top_k)

        # Q25 pinned injection: when query asks about vigência of all programs,
        # force one vigência chunk per non-PIBIC edital into context so the LLM
        # can enumerate all programs with full start/end/duration info.
        if _TODOS_PROGRAMAS_VIGENCIA_RE.search(query):
            _multi_pinned: list[dict] = []
            _multi_pids: set[str] = set()
            for _vq, _source_keys in _VIGENCIA_MULTI_EDITAL:
                _vq_expanded = await _pinned_search(
                    _vq,
                    top_k=10,
                    payload_filter=_RAG_PAYLOAD_FILTER,
                    embedding_provider=embedding_provider,
                    embedding_model=embedding_model,
                    source_contains=_source_keys,
                    cycle_filter=active_cycle,
                )
                if _vq_expanded and _vq_expanded[0]["parent_id"] not in _multi_pids:
                    _multi_pinned.append(_vq_expanded[0])
                    _multi_pids.add(_vq_expanded[0]["parent_id"])
            if _multi_pinned:
                # Always promote all pins to the front, deduplicated against
                # the existing list — see _promote_pinned for why "already
                # present but buried" must not short-circuit promotion.
                reranked_parents = _multi_pinned + [
                    p for p in reranked_parents if p["parent_id"] not in _multi_pids
                ]
                reranked_parents = reranked_parents[:context_top_k]

        # Q21 pinned injection: "mesmo colégio do orientador" for PIBICEM.
        # The seção 3.2.1 clause uses "lotado"/"obrigatoriedade"/"vinculado" —
        # terms absent from the query — so the chunk falls below reranker threshold.
        if _PIBICEM_COLEGIO_RE.search(query):
            _pc_expanded = await _pinned_search(
                _PIBICEM_COLEGIO_QUERY,
                top_k=20,
                payload_filter=_RAG_PAYLOAD_FILTER,
                embedding_provider=embedding_provider,
                embedding_model=embedding_model,
                source_contains=["pibicem", "pibic-em"],
                cycle_filter=active_cycle,
            )
            if _pc_expanded:
                reranked_parents = _promote_pinned(reranked_parents, _pc_expanded[0], context_top_k)

        # Q14 pinned injection: ICV relatório parcial — pin Aditivo nº 2 ICV chunk to
        # context position [0] so the LLM attributes the deadline to the correct document,
        # then pin the ICV edital's SIGAA sanções section to position [1].
        if _ICV_RELATORIO_PARCIAL_RE.search(query):
            _aditivo_filter = Filter(
                must=[FieldCondition(key="doc_type", match=MatchValue(value="aditivo"))],
            )
            _ad2_expanded = await _pinned_search(
                _ICV_ADITIVO_RELATORIO_QUERY,
                top_k=20,
                payload_filter=_aditivo_filter,
                embedding_provider=embedding_provider,
                embedding_model=embedding_model,
                source_contains=["icv"],
                # Page 2 chunks contain the updated chronogram (SIGAA + 17-31/03/2026).
                # Page 1 chunks contain "ADITIVO N° 2" text but NOT the new dates.
                page_number=2,
                cycle_filter=active_cycle,
            )
            if _ad2_expanded:
                # (The "ADITIVO: <label>" text prefix is now applied generically for
                # every doc_type="aditivo" parent inside _build_context — see Fase D.)
                reranked_parents = _promote_pinned(reranked_parents, _ad2_expanded[0], context_top_k)

            # Second injection: ICV edital Section 13 establishes "exclusivamente via
            # SIGAA" for relatório submissions. Without it the LLM omits SIGAA because
            # the aditivo chronogram only labels SIGAA for inscriptions/bolsista, not
            # for "Envio de Relatório parcial".
            _icv_edital_filter = Filter(
                must=[FieldCondition(key="doc_type", match=MatchValue(value="edital"))],
            )
            _icv_sanc_exp = await _pinned_search(
                "exclusivamente sistema SIGAA relatório envio prazo ICV cronograma sanções",
                top_k=10,
                payload_filter=_icv_edital_filter,
                embedding_provider=embedding_provider,
                embedding_model=embedding_model,
                source_contains=["icv"],
                text_contains=["sigaa", "relat"],
                cycle_filter=active_cycle,
            )
            if _icv_sanc_exp and reranked_parents:
                # Always promote to position [1] (position [0] is the aditivo
                # pin above), deduplicated — same reasoning as _promote_pinned.
                _sanc_pid = _icv_sanc_exp[0]["parent_id"]
                _rest = [p for p in reranked_parents[1:] if p["parent_id"] != _sanc_pid]
                reranked_parents = (
                    [reranked_parents[0], _icv_sanc_exp[0]] + _rest[:context_top_k - 2]
                )

        # Q03/Q10 pinned injection: see _PIBIC_DISCENTE_QUERY comment above.
        if _PIBIC_DISCENTE_RE.search(query):
            _pibic_disc_exp = await _pinned_search(
                _PIBIC_DISCENTE_QUERY,
                top_k=20,
                payload_filter=_RAG_PAYLOAD_FILTER,
                embedding_provider=embedding_provider,
                embedding_model=embedding_model,
                source_contains=["PIBIC_e_PIBIC_Af"],
                page_number=2,
                cycle_filter=active_cycle,
            )
            if _pibic_disc_exp:
                reranked_parents = _promote_pinned(reranked_parents, _pibic_disc_exp[0], context_top_k)

        # Q19 pinned injection: see _PIBITI_ORIENTACAO_QUERY comment above.
        if _PIBITI_COORIENTADOR_RE.search(query):
            _piti_exp = await _pinned_search(
                _PIBITI_ORIENTACAO_QUERY,
                top_k=20,
                payload_filter=_RAG_PAYLOAD_FILTER,
                embedding_provider=embedding_provider,
                embedding_model=embedding_model,
                source_contains=["PIBITI"],
                doc_type="edital",
                page_number=3,
                # page 3 has multiple parent blocks sharing the same generic
                # "4.1.x deveres do orientador" boilerplate; without requiring
                # the literal word, the highest-RRF-score block is often the
                # wrong one (see Q19 regression after enabling child overlap).
                text_contains=["coorientador"],
                cycle_filter=active_cycle,
            )
            if _piti_exp:
                reranked_parents = _promote_pinned(reranked_parents, _piti_exp[0], context_top_k)

        # Q24 pinned injection: see _ICV_PIBIC_NATUREZA_RE comment above.
        if _ICV_PIBIC_NATUREZA_RE.search(query):
            _natureza_pinned: list[dict] = []
            _natureza_pids: set[str] = set()
            for _nq, _nsrc in (
                (_ICV_VOLUNTARIA_QUERY, "ICV"),
                (_PIBIC_BOLSA_QUERY, "PIBIC_e_PIBIC_Af"),
            ):
                _n_exp = await _pinned_search(
                    _nq,
                    top_k=10,
                    payload_filter=_RAG_PAYLOAD_FILTER,
                    embedding_provider=embedding_provider,
                    embedding_model=embedding_model,
                    source_contains=[_nsrc],
                    cycle_filter=active_cycle,
                )
                if _n_exp and _n_exp[0]["parent_id"] not in _natureza_pids:
                    _natureza_pinned.append(_n_exp[0])
                    _natureza_pids.add(_n_exp[0]["parent_id"])
            if _natureza_pinned:
                reranked_parents = _natureza_pinned + [
                    p for p in reranked_parents if p["parent_id"] not in _natureza_pids
                ]
                reranked_parents = reranked_parents[:context_top_k]

        # ------------------------------------------------------------------ #
        # edital_ref bidirectional context expansion                         #
        # Connects aditivos to their parent editais via the edital_ref       #
        # metadata field. Two directions:                                     #
        # 1. Forward: aditivo is in context → pull parent edital chunks so   #
        #    the LLM sees both the original rule and the amendment together.  #
        # 2. Reverse: edital is in context → pull relevant aditivo chunks    #
        #    that reference it, surfacing amendments the query would miss     #
        #    (e.g. updated deadlines in Aditivo nº 2 for Q14).               #
        # Both directions do Python-side substring matching on display_name   #
        # vs edital_ref — no Qdrant index required.                          #
        # ------------------------------------------------------------------ #
        _eref_existing = {p["parent_id"] for p in reranked_parents}

        # Direction 1 — forward (aditivo in context → parent edital)
        _aditivo_edital_refs = list(dict.fromkeys(
            p["edital_ref"]
            for p in reranked_parents
            if p.get("doc_type") == "aditivo" and p.get("edital_ref")
        ))
        for _eref in _aditivo_edital_refs:
            _eref_lower = _eref.lower()
            _eref_pts = await hybrid_search(
                query,
                top_k=20,
                payload_filter=_RAG_PAYLOAD_FILTER,
                embedding_provider=embedding_provider,
                embedding_model=embedding_model,
            )
            _eref_filtered = [
                pt for pt in _eref_pts
                if _eref_lower in (pt.payload.get("display_name") or "").lower()
                and (pt.payload.get("doc_type") or "") != "aditivo"
            ]
            if _eref_filtered:
                _eref_expanded = expand_to_parents(_eref_filtered[:2])
                if _eref_expanded and _eref_expanded[0]["parent_id"] not in _eref_existing:
                    reranked_parents.append(_eref_expanded[0])
                    _eref_existing.add(_eref_expanded[0]["parent_id"])

        # Direction 2 — reverse (edital in context → relevant aditivos)
        _ctx_display_names_lower = {
            p["display_name"].lower()
            for p in reranked_parents
            if p.get("doc_type") != "aditivo" and p.get("display_name")
        }
        if _ctx_display_names_lower:
            _aditivo_only_filter = Filter(
                must=[FieldCondition(key="doc_type", match=MatchValue(value="aditivo"))],
            )
            _aditivo_pts = await hybrid_search(
                query,
                top_k=20,
                payload_filter=_aditivo_only_filter,
                embedding_provider=embedding_provider,
                embedding_model=embedding_model,
            )
            _matched_aditivos = [
                pt for pt in _aditivo_pts
                if (pt.payload.get("edital_ref") or "") and any(
                    (pt.payload.get("edital_ref") or "").lower() in dname
                    or dname in (pt.payload.get("edital_ref") or "").lower()
                    for dname in _ctx_display_names_lower
                )
            ]
            if _matched_aditivos:
                _aditivo_expanded = expand_to_parents(_matched_aditivos[:3])
                for _ap in _aditivo_expanded[:2]:
                    if _ap["parent_id"] not in _eref_existing:
                        reranked_parents.append(_ap)
                        _eref_existing.add(_ap["parent_id"])

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
