# AGENTS.md — PROPESQI RAG Chatbot

Sistema de Q&A sobre documentos institucionais da PROPESQI/UFPI, executado
inteiramente on-premise com LLM local (gemma3:12b) numa NVIDIA RTX 5060 Ti 16 GB.

Consulte [DOCUMENTATION.md](DOCUMENTATION.md) para a referência técnica completa
e [PLANEJAMENTO.md](PLANEJAMENTO.md) para decisões de arquitetura e modelos.

---

## Arquitetura

| Camada              | Tecnologia                                 |
|---------------------|--------------------------------------------|
| Frontend            | React 18 + Vite + TypeScript + Tailwind    |
| Backend             | FastAPI (Python 3.11+) + SQLAlchemy async  |
| Banco relacional    | PostgreSQL 16 (`init/01_schema.sql`)       |
| Vector DB           | Qdrant (named vectors: `dense` + `sparse`) |
| LLM / Embeddings    | Ollama → `gemma3:12b` / `bge-m3`          |
| Reranker            | `BAAI/bge-reranker-v2-m3` (sentence-transformers, CPU) |
| Encoder esparso     | fastembed BM42                             |
| Infraestrutura      | Docker Compose + overlay GPU               |

Pipeline RAG (`backend/app/core/rag_engine.py`):
`Normalização → HyDE → Multi-query → Hybrid Search (RRF) → Rerank → Compressão contextual → LLM streaming`

---

## Build & Teste

### Backend
```bash
# A partir de backend/
pip install -r requirements.txt

# Testes de latência (sem servidor HTTP — in-process via ASGI)
pytest tests/latency/ -v

# Testes de carga (requer stack Docker rodando)
locust -f tests/load/locustfile.py --host http://localhost:8000 \
       --users 20 --spawn-rate 5 --run-time 2m --headless
```

### Frontend
```bash
# A partir de frontend/
npm install
npm run dev      # servidor de desenvolvimento
npm run build    # build de produção (tsc + vite build)
```

### Docker (produção com GPU)
```bash
# Subir toda a stack com suporte a GPU
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d

# Apenas CPU
docker compose up -d
```

---

## Convenções Críticas

### Qdrant — vetores nomeados
A coleção usa vetores nomeados. **Sempre** referencie via constantes:
```python
from app.db.qdrant import DENSE_VECTOR_NAME, SPARSE_VECTOR_NAME  # "dense" / "sparse"
```
Nunca passe vetores sem nome (formato legado): isso quebra silenciosamente
a busca híbrida. Ver `backend/app/db/qdrant.py`.

### Settings — singleton cacheado
Sempre use `get_settings()` (decorada com `@lru_cache`). Nunca instancie
`Settings()` diretamente para não contornar o cache.
`SECRET_KEY` deve ter ≥ 32 caracteres; a validação explode na inicialização.

### SQLAlchemy — modo assíncrono
Toda interação com o banco usa `AsyncSession` e `asyncpg`. Não misture
drivers síncronos (`psycopg2`). ORM via `AsyncSessionLocal` em `app/db/postgres.py`.

### Autenticação
- Chat público (`/chat/*`) — **sem autenticação**.
- Painel admin (`/admin/*`, `/documents/*`, `/evaluation/*`) — **JWT obrigatório**.
- Tokens: access (60 min) + refresh (7 dias). Implementado em `app/core/security.py`.

### Progresso de indexação
Eventos de progresso são publicados via SSE em `app/core/progress.py` e
consumidos pelo frontend via WebSocket em `/ws`. Não use `print()`/logging
para reportar progresso ao cliente.

### Configuração RAG ajustável em runtime
Parâmetros RAG (threshold do reranker, temperatura HyDE, etc.) são lidos
do banco via `app/db/rag_config.py`. O painel admin altera esses valores
sem reiniciar o serviço.

### Primeiro uso — fastembed BM42
O encoder esparso baixa ~100 MB de modelo na **primeira execução**.
Em ambientes sem acesso à internet, pré-baixe o modelo ou monte o cache
como volume Docker.

### API — prefixo `/api`
O frontend aponta para `API_BASE = '/api'`. O Nginx (`frontend/nginx.conf`)
faz proxy desse prefixo para o backend na porta 8000. Não acesse o backend
diretamente pela porta em produção.

### pytest — asyncio automático
`pyproject.toml` configura `asyncio_mode = "auto"`. Todos os testes `async def`
são executados automaticamente. O `conftest.py` popula `os.environ.setdefault`
antes de importar qualquer módulo da app.

---

## Variáveis de Ambiente Obrigatórias

| Variável                    | Descrição                               |
|-----------------------------|-----------------------------------------|
| `DATABASE_URL`              | PostgreSQL asyncpg URL                  |
| `QDRANT_URL`                | URL do Qdrant                           |
| `QDRANT_API_KEY`            | Chave de API do Qdrant                  |
| `OLLAMA_BASE_URL`           | URL base do Ollama                      |
| `SECRET_KEY`                | Segredo JWT (≥ 32 chars)                |
| `POSTGRES_USER/PASSWORD/DB` | Usadas pelo `docker-compose.yml`        |
| `PROPESQI_APP_PASSWORD`     | Senha da role de aplicação PostgreSQL   |

Gere `SECRET_KEY` com:
```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

---

## Armadilhas Comuns

- **Coleção Qdrant incompatível**: Se a coleção existir com config antiga
  (vetor único sem nome), `ensure_collection()` apaga e recria — todos os
  dados indexados são perdidos. Faça backup antes de migrar.
- **bcrypt versão**: `requirements.txt` fixa `bcrypt>=3.0,<4.0`. bcrypt 4+
  tem API diferente; não atualize sem testar `passlib`.
- **OCR via API cloud**: PDFs digitalizados são enviados para a API
  LLMWhisperer (`LLMWHISPERER_API_KEY`), sem Tesseract/OpenCV local. Roda em
  background task, fora do request de upload.
- **RAGAS requer LLM**: `app/api/routes/evaluation.py` chama o Ollama para
  métricas RAGAS. Não execute avaliações quando o Ollama não estiver disponível.
