"""
run_groundtruth_eval.py — Live evaluation runner for groundtruth_chatbot_rag.csv.

For each question in the groundtruth CSV this script:
  1. Calls the live chat pipeline (POST /api/chat/stream on the running
     Docker Compose stack) and captures the full streamed answer plus the
     cited source documents.
  2. Sends the answer, the expected answer, keywords and source to a Gemini
     model acting as an LLM judge, which scores the rubric columns already
     present in the CSV header (corretude_factual_0_1, completude_0_1,
     citacao_fonte_0_1, alucinacao_1_sem_0_com, relevancia_0_1,
     pontuacao_total_0_5, observacoes_avaliador).

Writes a new CSV with every column filled. The original groundtruth file is
never modified.

Requirements:
  - Full stack running (docker compose up) and reachable at --base-url.
  - GOOGLE_API_KEY set in the repo-root .env (used both as judge and,
    depending on rag_config, as the chat LLM provider).

Usage (from backend/):
    python tests/run_groundtruth_eval.py
    python tests/run_groundtruth_eval.py --limit 3          # smoke test
    python tests/run_groundtruth_eval.py --ids Q01,Q05,Q20  # specific rows
"""

import argparse
import csv
import json
import os
import sys
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY", "")
JUDGE_MODEL = "gemini-3.1-flash-lite"
GEMINI_URL = (
    f"https://generativelanguage.googleapis.com/v1beta/models/{JUDGE_MODEL}:generateContent"
)

DEFAULT_INPUT = Path(__file__).with_name("groundtruth_chatbot_rag.csv")
DEFAULT_OUTPUT = Path(__file__).with_name("groundtruth_chatbot_rag_resultados.csv")
DEFAULT_BASE_URL = "http://localhost:3000/api"

# gemini-3.1-flash-lite free tier: 15 requests/minute. Each row makes two
# Gemini calls (one inside /chat/stream for the answer, one for the judge),
# so pace every Gemini-consuming call to stay under the limit.
_GEMINI_RPM = 15
# With HyDE + multi-query enabled, each /chat/stream internally fires up to 3
# Gemini calls (HyDE, reformulations, final generation) before the judge call.
# Use 4 "slots" per row so the combined burst stays inside the RPM budget.
_GEMINI_CALLS_PER_CHAT = 3  # HyDE + multiquery + generation (worst case sem compressão)
_MIN_GEMINI_INTERVAL = (60.0 / _GEMINI_RPM) * _GEMINI_CALLS_PER_CHAT
_last_gemini_call = 0.0


def _rate_limit_gemini() -> None:
    global _last_gemini_call
    now = time.monotonic()
    wait = _MIN_GEMINI_INTERVAL - (now - _last_gemini_call)
    if wait > 0:
        time.sleep(wait)
    _last_gemini_call = time.monotonic()

FIELDNAMES = [
    "id", "programa", "categoria", "dificuldade", "tipo_resposta", "pergunta",
    "resposta_esperada", "palavras_chave", "fonte", "resposta_chatbot",
    "tempo_resposta_s",
    "corretude_factual_0_1", "completude_0_1", "citacao_fonte_0_1",
    "alucinacao_1_sem_0_com", "relevancia_0_1", "pontuacao_total_0_5",
    "observacoes_avaliador",
]

JUDGE_PROMPT_TEMPLATE = """\
Você é um avaliador especialista em sistemas de Perguntas e Respostas (RAG) \
institucionais da UFPI/PROPESQI.

Compare a RESPOSTA DO CHATBOT com a RESPOSTA ESPERADA (gabarito) abaixo e \
atribua notas objetivas.

PERGUNTA:
{pergunta}

RESPOSTA ESPERADA (gabarito):
{resposta_esperada}

PALAVRAS-CHAVE ESPERADAS: {palavras_chave}

FONTE ESPERADA: {fonte}

RESPOSTA DO CHATBOT:
{resposta_chatbot}

DOCUMENTOS CITADOS PELO CHATBOT COMO FONTE:
{sources_text}

Avalie e responda APENAS com um objeto JSON (sem markdown, sem texto extra) \
no formato exato:
{{
  "corretude_factual_0_1": <número de 0 a 1, com até 2 casas decimais — o \
quanto os fatos da resposta do chatbot conferem com o gabarito>,
  "completude_0_1": <número de 0 a 1 — o quanto a resposta cobre os pontos \
do gabarito>,
  "citacao_fonte_0_1": <número de 0 a 1 — 1 se os documentos citados \
correspondem à fonte esperada, 0 se não houver correspondência>,
  "alucinacao_1_sem_0_com": <1 se a resposta NÃO contém informação \
inventada/incorreta não suportada pelo gabarito, 0 se CONTÉM alucinação>,
  "relevancia_0_1": <número de 0 a 1 — o quanto a resposta é relevante e \
direta para a pergunta feita>,
  "pontuacao_total_0_5": <número de 0 a 5 — avaliação geral da qualidade da \
resposta>,
  "observacoes_avaliador": "<1-2 frases em português explicando os \
principais acertos e/ou problemas>"
}}"""


def call_chat_stream(client: httpx.Client, base_url: str, question: str) -> tuple[str, list[dict]]:
    """POST /chat/stream and parse the SSE response into (answer, sources)."""
    answer_parts: list[str] = []
    sources: list[dict] = []
    event_type: str | None = None
    data_lines: list[str] = []

    _rate_limit_gemini()
    with client.stream(
        "POST", f"{base_url}/chat/stream", json={"message": question}, timeout=180.0
    ) as resp:
        resp.raise_for_status()
        for raw_line in resp.iter_lines():
            line = raw_line.rstrip("\r")
            if line.startswith("event:"):
                event_type = line[len("event:"):].strip()
                data_lines = []
            elif line.startswith("data:"):
                # Per the SSE spec, only a single leading space after "data:"
                # is a delimiter — stripping more would eat real leading
                # spaces from streamed text tokens (e.g. "Os objetivos").
                content = line[len("data:"):]
                if content.startswith(" "):
                    content = content[1:]
                data_lines.append(content)
            elif line == "" and event_type is not None:
                data = "\n".join(data_lines)
                if event_type == "token":
                    answer_parts.append(data)
                elif event_type == "sources":
                    try:
                        sources = json.loads(data)
                    except json.JSONDecodeError:
                        sources = []
                event_type = None
                data_lines = []

    return "".join(answer_parts), sources


def call_gemini_judge(client: httpx.Client, row: dict, resposta_chatbot: str, sources: list[dict]) -> dict:
    sources_text = "\n".join(
        f"- {s.get('display_name') or s.get('original_name', '')} (p. {s.get('page_number', '?')})"
        for s in sources
    ) or "(nenhuma fonte retornada)"

    prompt = JUDGE_PROMPT_TEMPLATE.format(
        pergunta=row["pergunta"],
        resposta_esperada=row["resposta_esperada"],
        palavras_chave=row["palavras_chave"],
        fonte=row["fonte"],
        resposta_chatbot=resposta_chatbot or "(resposta vazia)",
        sources_text=sources_text,
    )

    _rate_limit_gemini()
    resp = client.post(
        GEMINI_URL,
        params={"key": GOOGLE_API_KEY},
        json={
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.0,
                "maxOutputTokens": 512,
                "responseMimeType": "application/json",
            },
        },
        timeout=120.0,
    )
    resp.raise_for_status()
    text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
    return json.loads(text)


def _request_with_retries(fn, *args, retries: int = 3, base_delay: float = 5.0, **kwargs):
    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            return fn(*args, **kwargs)
        except (httpx.HTTPError, json.JSONDecodeError, KeyError) as exc:
            last_exc = exc
            if attempt < retries - 1:
                time.sleep(base_delay * (attempt + 1))
    raise last_exc  # type: ignore[misc]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--limit", type=int, default=None, help="Only run the first N rows")
    parser.add_argument("--ids", default=None, help="Comma-separated list of question ids to run (e.g. Q01,Q05)")
    args = parser.parse_args()

    if not GOOGLE_API_KEY:
        print("ERROR: GOOGLE_API_KEY not found in environment / .env", file=sys.stderr)
        return 1

    with args.input.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    if args.ids:
        wanted = {s.strip() for s in args.ids.split(",") if s.strip()}
        rows = [r for r in rows if r["id"] in wanted]
    elif args.limit:
        rows = rows[: args.limit]

    results: list[dict] = []
    with httpx.Client() as client:
        for row in rows:
            row = dict(row)
            qid = row["id"]
            print(f"[{qid}] Pergunta: {row['pergunta'][:80]}...")

            t0 = time.monotonic()
            try:
                answer, sources = _request_with_retries(
                    call_chat_stream, client, args.base_url, row["pergunta"]
                )
                row["tempo_resposta_s"] = round(time.monotonic() - t0, 2)
            except Exception as exc:
                print(f"[{qid}] ERRO no /chat/stream: {exc}", file=sys.stderr)
                row["resposta_chatbot"] = ""
                row["tempo_resposta_s"] = ""
                row["observacoes_avaliador"] = f"ERRO /chat/stream: {exc}"
                results.append(row)
                continue

            row["resposta_chatbot"] = answer
            print(f"[{qid}] Resposta ({len(answer)} chars, {row['tempo_resposta_s']}s): {answer[:120]}...")

            try:
                scores = _request_with_retries(call_gemini_judge, client, row, answer, sources)
            except Exception as exc:
                print(f"[{qid}] ERRO no judge: {exc}", file=sys.stderr)
                row["observacoes_avaliador"] = f"ERRO judge: {exc}"
                results.append(row)
                continue

            for key in (
                "corretude_factual_0_1", "completude_0_1", "citacao_fonte_0_1",
                "alucinacao_1_sem_0_com", "relevancia_0_1", "pontuacao_total_0_5",
                "observacoes_avaliador",
            ):
                row[key] = scores.get(key, "")

            print(f"[{qid}] Pontuação total: {row.get('pontuacao_total_0_5')}/5")
            results.append(row)

    with args.output.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        for row in results:
            writer.writerow({k: row.get(k, "") for k in FIELDNAMES})

    print(f"\nResultados salvos em: {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
