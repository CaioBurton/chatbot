# PROPESQI RAG Chatbot

Assistente virtual institucional da Pró-Reitoria de Pesquisa e Inovação (PROPESQI) da Universidade Federal do Piauí (UFPI). Responde dúvidas sobre editais, resoluções e regulamentos de programas de iniciação científica com base em documentos indexados. Suporta dois modos de LLM: local (Ollama/gemma3:12b, sem internet) ou via API externa (Gemini, OpenAI, Anthropic).

## Requisitos

O sistema suporta dois modos de operação com requisitos diferentes:

### Modo local (Ollama + gemma3:12b)

Totalmente on-premise, sem chamadas a APIs externas. Requer GPU dedicada.

| Componente | Versão mínima |
|---|---|
| Docker + Docker Compose | 24+ |
| NVIDIA Container Toolkit | qualquer |
| GPU NVIDIA | 16 GB VRAM recomendado |
| VRAM disponível | ~9 GB (bge-m3 + gemma3:12b Q4_K_M) |

### Modo externo (Gemini / OpenAI / Anthropic)

Usa uma API de LLM externa para geração de respostas. **Não requer GPU.** O embeddings (`bge-m3`) e o reranker continuam rodando via Ollama localmente.

| Componente | Requisito |
|---|---|
| Docker + Docker Compose | 24+ |
| GPU NVIDIA | não obrigatória |
| API key | `GOOGLE_API_KEY`, `OPENAI_API_KEY` ou `ANTHROPIC_API_KEY` |

> O `llm_provider` e o modelo são configuráveis em runtime pelo painel admin sem reiniciar o serviço. O modo externo com `gemini-3.1-flash-lite` é o utilizado nos ciclos de otimização RAG e no harness de avaliação (`run_groundtruth_eval.py`).

## Início rápido

```bash
# 1. Clone e entre na pasta
git clone <url-do-repositorio>
cd chatbot

# 2. Configure as variáveis de ambiente
cp .env.example .env
# Edite .env e substitua todos os CHANGE_ME por valores reais

# 3. Gere uma SECRET_KEY segura (≥ 32 caracteres)
python3 -c "import secrets; print(secrets.token_hex(32))"

# 4. Suba o stack completo (GPU habilitada por padrão)
docker compose up -d

# 5. Aguarde todos os serviços ficarem saudáveis (~2 min na primeira vez)
docker compose ps

# 6. Acesse a interface em http://localhost:3000
```

Na primeira execução o Ollama baixa automaticamente os modelos `gemma3:12b` e `bge-m3` (~9 GB). Para usar um LLM externo em vez do gemma3, configure `llm_provider` no painel admin após subir o stack.

## Arquitetura

```
Usuário → http://localhost:3000
              │
         Nginx (frontend)
              │ /api/*
         FastAPI :8000 (backend)
              │
     ┌────────┼────────────┐
     │        │            │
 PostgreSQL  Qdrant     Ollama
  (sessões)  (vetores)  (LLM + embeddings)
```

**Pipeline RAG** (`backend/app/core/rag_engine.py`):

```
Query → Normalização → HyDE → Multi-query → Hybrid Search RRF
      → Rerank (bge-reranker-v2-m3) → Expansão edital_ref
      → Compressão contextual → LLM streaming (SSE)
```

### Stack tecnológico

| Camada | Tecnologia |
|---|---|
| Frontend | React 18 + Vite + TypeScript + Tailwind CSS |
| Backend | FastAPI (Python 3.11+) + SQLAlchemy 2.0 async |
| Banco relacional | PostgreSQL 16 |
| Banco vetorial | Qdrant (vetores `dense` + `sparse`) |
| LLM | Ollama → `gemma3:12b` (local) ou Gemini / OpenAI / Anthropic (externo) |
| Embeddings | Ollama → `bge-m3` |
| Reranker | `BAAI/bge-reranker-v2-m3` (sentence-transformers, CPU) |
| Encoder esparso | fastembed BM42 |
| Infraestrutura | Docker Compose + GPU overlay |

## Configuração (`.env`)

| Variável | Descrição |
|---|---|
| `POSTGRES_USER` / `POSTGRES_PASSWORD` | Credenciais do superusuário PostgreSQL |
| `POSTGRES_DB` | Nome do banco de dados |
| `PROPESQI_APP_PASSWORD` | Senha do papel de aplicação (menor privilégio) |
| `DATABASE_URL` | URL de conexão asyncpg para o backend |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` | Primeiro usuário admin (criado no startup) |
| `QDRANT_URL` | URL interna do Qdrant (`http://qdrant:6333`) |
| `QDRANT_API_KEY` | Chave de autenticação do Qdrant (≥ 32 chars) |
| `OLLAMA_BASE_URL` | URL interna do Ollama (`http://ollama:11434`) |
| `SECRET_KEY` | Chave para assinatura JWT (≥ 32 chars) |
| `ALGORITHM` | Algoritmo JWT (padrão: `HS256`) |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Validade do access token (padrão: 60) |
| `REFRESH_TOKEN_EXPIRE_DAYS` | Validade do refresh token (padrão: 7) |
| `ALLOWED_ORIGINS` | Origens CORS permitidas |
| `VITE_API_URL` | URL base da API para o build do frontend (padrão: `/api`) |
| `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` / `GOOGLE_API_KEY` | Opcionais — apenas se `llm_provider != 'local'` |

## Gerenciamento de documentos

O painel admin (acesso via login em `/`) permite:

- **Upload de PDFs** — nativos ou escaneados (OCR automático via API cloud LLMWhisperer)
- **Tipos de documento:** `edital`, `aditivo`, `resolucao`, `tutorial`, `portaria`, `relatorio`
- **Aditivos:** ao selecionar o tipo `aditivo`, um campo opcional "Edital de referência" aparece. Preenchê-lo com o nome do edital pai (ex.: `Edital ICV 2025/2026`) ativa a expansão bidirecional de contexto no pipeline RAG
- **Reindexação:** documentos com erro podem ser reprocessados individualmente

### Como indexar documentos

1. Faça login com as credenciais de admin
2. Acesse a aba **Documentos**
3. Arraste PDFs para a área de upload ou clique para selecionar
4. Preencha o tipo, nome de exibição e link opcional
5. Acompanhe o progresso de indexação em tempo real

## API

| Rota | Auth | Descrição |
|---|---|---|
| `POST /api/auth/login` | — | Login, retorna access + refresh tokens |
| `POST /api/auth/refresh` | — | Renova access token |
| `GET /api/chat/stream` | — | Q&A via SSE streaming |
| `POST /api/documents/upload` | JWT admin | Upload de PDF |
| `GET /api/documents` | JWT admin | Lista documentos |
| `POST /api/documents/{id}/reindex` | JWT admin | Reindexar documento |
| `GET /api/admin/rag-config` | JWT admin | Lê parâmetros RAG |
| `PUT /api/admin/rag-config` | JWT admin | Ajusta parâmetros RAG em runtime |
| `GET /health` | — | Health check |

Os parâmetros RAG (threshold do reranker, temperatura HyDE, top-k) são ajustáveis em runtime pelo painel admin sem reiniciar o serviço.

## Desenvolvimento local

### Backend

```bash
cd backend
pip install -r requirements.txt

# Testes de latência (sem servidor rodando)
pytest tests/latency/ -v

# Testes de carga (requer stack Docker rodando)
locust -f tests/load/locustfile.py --host http://localhost:8000 \
       --users 20 --spawn-rate 5 --run-time 2m --headless
```

### Frontend

```bash
cd frontend
npm install
npm run dev      # dev server com hot reload em http://localhost:5173
npm run build    # build de produção (tsc + vite → dist/)
```

### Rebuild após mudanças no código

```bash
# Backend (Python)
docker compose build backend && docker compose up -d backend

# Frontend (React)
docker compose build frontend && docker compose up -d frontend

# Ambos
docker compose build backend frontend && docker compose up -d backend frontend
```

## Estrutura do projeto

```
chatbot/
├── backend/
│   ├── app/
│   │   ├── api/routes/       # auth, chat, documents, admin, evaluation
│   │   ├── core/
│   │   │   ├── rag_engine.py # pipeline RAG completo (HyDE, rerank, SSE)
│   │   │   ├── config.py     # Settings singleton (@lru_cache)
│   │   │   └── security.py   # JWT (access 60 min / refresh 7 dias)
│   │   ├── db/
│   │   │   ├── qdrant.py     # gerenciamento da coleção + constantes de vetores
│   │   │   ├── postgres.py   # AsyncSessionLocal factory
│   │   │   ├── search.py     # hybrid_search + expand_to_parents
│   │   │   └── rag_config.py # parâmetros RAG ajustáveis em runtime
│   │   ├── ingestion/
│   │   │   ├── processor.py  # pipeline de ingestão de PDF
│   │   │   ├── chunker.py    # hierarquia parent→child chunks
│   │   │   └── sparse.py     # encoder BM42
│   │   └── models/           # SQLAlchemy ORM (Document, ChatSession, …)
│   ├── tests/
│   │   ├── latency/          # testes ASGI in-process
│   │   ├── load/             # locustfile para testes de carga
│   │   └── run_groundtruth_eval.py  # avaliação com ground truth (judge: gemini-3.1-flash-lite)
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── admin/        # UploadZone, UploadMetadataModal, painel RAG
│   │   │   └── chat/         # interface de chat SSE
│   │   └── lib/              # api.ts, uuid.ts
│   └── nginx.conf            # proxy reverso /api → backend:8000
├── init/
│   ├── 00_roles.sh           # cria papel de menor privilégio
│   ├── 01_schema.sql         # schema + migrações idempotentes
│   └── 02_seed_admin.sh      # seed do primeiro admin
├── docker-compose.yml
├── .env.example
└── CLAUDE.md
```

## Observações de produção

- **Segredos:** nunca comite o arquivo `.env`. Use um gerenciador de segredos ou variáveis de ambiente do sistema em produção.
- **CORS:** restrinja `ALLOWED_ORIGINS` ao hostname real do frontend em produção.
- **Uploads grandes:** PDFs escaneados podem levar vários minutos. O timeout de upload no nginx deve ser ajustado adequadamente.
- **VRAM:** `OLLAMA_NUM_PARALLEL=1` evita OOM em GPUs com 16 GB. Aumentar apenas se houver VRAM disponível. No modo externo (Gemini/OpenAI), o Ollama ainda é usado para embeddings (`bge-m3`) mas não carrega o gemma3:12b, liberando toda a VRAM.
- **fastembed BM42:** baixa ~100 MB de modelo na primeira execução. Em ambientes offline, pré-baixe e monte como volume Docker.
- **Qdrant:** se a coleção existente tiver configuração legada (vetor único), `ensure_collection()` **recria a coleção** — todos os dados indexados são perdidos. Faça backup antes de migrar.
