# Documentação Técnica — PROPESQI RAG Chatbot

Sistema de perguntas e respostas sobre documentos internos da Pró-Reitoria de Pesquisa e Inovação (PROPESQI) da Universidade Federal do Piauí (UFPI), operando inteiramente on-premise com LLM local em GPU NVIDIA RTX 5060 Ti 16 GB VRAM.

---

## Sumário

1. [Visão Geral](#1-visão-geral)
2. [Arquitetura](#2-arquitetura)
3. [Stack Tecnológica](#3-stack-tecnológica)
4. [Estrutura de Diretórios](#4-estrutura-de-diretórios)
5. [Backend](#5-backend)
   - 5.1 [Configuração](#51-configuração)
   - 5.2 [API REST](#52-api-rest)
   - 5.3 [Autenticação e Autorização](#53-autenticação-e-autorização)
   - 5.4 [Pipeline RAG](#54-pipeline-rag)
   - 5.5 [Ingestão de Documentos](#55-ingestão-de-documentos)
   - 5.6 [Busca Híbrida](#56-busca-híbrida)
   - 5.7 [Reranking](#57-reranking)
   - 5.8 [Avaliação (RAGAS)](#58-avaliação-ragas)
   - 5.9 [WebSocket — Progresso de Indexação](#59-websocket--progresso-de-indexação)
6. [Banco de Dados](#6-banco-de-dados)
   - 6.1 [PostgreSQL — Esquema Relacional](#61-postgresql--esquema-relacional)
   - 6.2 [Qdrant — Coleção de Vetores](#62-qdrant--coleção-de-vetores)
7. [Frontend](#7-frontend)
8. [Modelos de IA](#8-modelos-de-ia)
9. [Segurança](#9-segurança)
10. [Implantação com Docker](#10-implantação-com-docker)
11. [Variáveis de Ambiente](#11-variáveis-de-ambiente)
12. [Testes](#12-testes)

---

## 1. Visão Geral

O sistema permite que usuários da UFPI façam perguntas em linguagem natural sobre documentos institucionais da PROPESQI (editais, resoluções, regulamentos, etc.) e recebam respostas fundamentadas exclusivamente no conteúdo indexado, com citação das fontes.

**Características principais:**
- Chat público (sem login) com streaming de respostas via SSE
- Painel administrativo protegido por JWT para upload, gestão e reindexação de documentos
- Pipeline RAG avançado: HyDE + multi-query + busca híbrida BM25/dense + reranking + compressão contextual
- Execução completamente on-premise — nenhum dado trafega para APIs externas
- Suporte a PDFs nativos e digitalizados (OCR)

---

## 2. Arquitetura

```
┌──────────────────────────────────────────────────────────────────┐
│                     FRONTEND (React + Vite)                      │
│  ┌─────────────────────┐   ┌──────────────────────────────────┐  │
│  │  Chat (público)     │   │  Painel Admin (autenticado)      │  │
│  │  • Streaming SSE    │   │  • Upload de PDFs                │  │
│  │  • Histórico        │   │  • Gestão CRUD de documentos     │  │
│  │  • Modo claro/escuro│   │  • Reindexação / parâmetros RAG  │  │
│  └──────────┬──────────┘   └──────────────┬─────────────────-─┘  │
└─────────────┼────────────────────────────-┼──────────────────────┘
              │  HTTP REST + SSE + WebSocket │
┌─────────────▼────────────────────────────-▼──────────────────────┐
│                    BACKEND (FastAPI / Python 3.11)                │
│                                                                   │
│  /auth   /documents   /chat   /admin   /evaluation   /ws         │
│                                                                   │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │                     RAG Core Engine                      │    │
│  │  1. Normalização  →  2. HyDE  →  3. Multi-query          │    │
│  │  4. Hybrid Search →  5. Rerank →  6. Compressão          │    │
│  │  7. Montagem de contexto  →  8. LLM Streaming            │    │
│  └────────────────┬──────────────────────┬───────────────---┘    │
└───────────────────┼──────────────────────┼───────────────────────┘
                    │                      │
     ┌──────────────▼──────┐  ┌────────────▼─────────┐  ┌──────────────────┐
     │  Qdrant             │  │  Ollama               │  │  PostgreSQL 16   │
     │  Hybrid Search      │  │  gemma3:12b (LLM)     │  │  Usuários        │
     │  BM42 + bge-m3      │  │  bge-m3 (embeddings)  │  │  Sessões / Chat  │
     │  RRF Fusion         │  │  GPU RTX 5060 Ti      │  │  Documentos      │
     └─────────────────────┘  └───────────────────────┘  └──────────────────┘
                    │
     ┌──────────────▼──────────────────────────────────────┐
     │             Pipeline de Ingestão de Documentos      │
     │  PDF nativo  →  pdfplumber / pypdf                   │
     │  PDF scan    →  OpenCV + Tesseract OCR               │
     │  Chunking    →  Parent-Child (tiktoken cl100k_base)  │
     │  Embeddings  →  bge-m3 via Ollama (batches de 32)    │
     └─────────────────────────────────────────────────────┘
```

---

## 3. Stack Tecnológica

| Camada | Tecnologia | Versão |
|--------|-----------|--------|
| Frontend | React + Vite + TypeScript | React 18 |
| Estilização | Tailwind CSS | — |
| Backend | FastAPI | ≥ 0.109 |
| Runtime Python | Python | 3.11+ |
| ORM | SQLAlchemy (async) | ≥ 2.0 |
| Driver PostgreSQL | asyncpg | ≥ 0.29 |
| Banco relacional | PostgreSQL | 16 |
| Vector database | Qdrant | ≥ 1.7 |
| LLM local | Ollama | — |
| LLM principal | gemma3:12b | — |
| Modelo de embeddings | BAAI/bge-m3 | 1024 dims |
| Encoder esparso | fastembed (BM42) | ≥ 0.3 |
| Reranker | BAAI/bge-reranker-v2-m3 | — |
| OCR | Tesseract 5 + OpenCV | — |
| Tokenizer | tiktoken (cl100k_base) | ≥ 0.6 |
| Autenticação | JWT (python-jose) + bcrypt | — |
| Avaliação RAG | RAGAS | ≥ 0.1 |
| Containerização | Docker Compose | v2+ |

---

## 4. Estrutura de Diretórios

```
chatbot/
├── docker-compose.yml          # Composição base (CPU)
├── docker-compose.gpu.yml      # Override GPU (NVIDIA RTX 5060 Ti)
├── PLANEJAMENTO.md             # Documento de planejamento do projeto
├── DOCUMENTATION.md            # Esta documentação
│
├── init/
│   ├── 00_roles.sh             # Cria role limitada no PostgreSQL
│   └── 01_schema.sql           # DDL — tabelas, índices, extensões
│
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app/
│       ├── main.py             # Ponto de entrada FastAPI
│       ├── api/routes/
│       │   ├── auth.py         # POST /auth/login
│       │   ├── chat.py         # /chat/sessions, /chat/stream, feedback
│       │   ├── documents.py    # Upload, CRUD, busca, reindexação
│       │   ├── admin.py        # Parâmetros RAG (GET/PUT)
│       │   ├── evaluation.py   # RAGAS evaluation
│       │   └── ws.py           # WebSocket progresso de indexação
│       ├── core/
│       │   ├── config.py       # Settings via pydantic-settings
│       │   ├── security.py     # JWT, bcrypt, depend. de autorização
│       │   ├── rag_engine.py   # Pipeline RAG completo + streaming SSE
│       │   ├── evaluator.py    # Lógica de avaliação RAGAS
│       │   ├── progress.py     # Pub/sub in-process para progresso
│       │   └── document_names.py # Normalização de nomes de exibição
│       ├── db/
│       │   ├── postgres.py     # Engine AsyncSA + fábrica de sessão
│       │   ├── qdrant.py       # Cliente Qdrant singleton + ensure_collection
│       │   ├── search.py       # hybrid_search() + expand_to_parents()
│       │   ├── reranker.py     # rerank() via sentence-transformers
│       │   └── rag_config.py   # Configurações dinâmicas RAG (DB)
│       ├── ingestion/
│       │   ├── processor.py    # Orquestrador do pipeline de ingestão
│       │   ├── chunker.py      # Parent-child chunking com tiktoken
│       │   ├── sparse.py       # Encoder esparso BM42 via fastembed
│       │   └── extractors/
│       │       ├── pdf.py      # Extração nativa (pdfplumber/pypdf)
│       │       └── ocr.py      # OCR com OpenCV + Tesseract
│       ├── models/             # SQLAlchemy ORM models
│       └── schemas/            # Pydantic request/response schemas
│
└── frontend/
    ├── src/
    │   ├── App.tsx             # Roteamento de views (chat/admin)
    │   ├── components/
    │   │   ├── chat/           # ChatWindow, MessageBubble, ChatInput
    │   │   ├── admin/          # AdminPanel, DocumentTable, UploadZone…
    │   │   └── layout/         # Sidebar
    │   ├── hooks/
    │   │   ├── useAuth.ts      # Estado de autenticação
    │   │   ├── useChat.ts      # Streaming SSE + histórico
    │   │   ├── useSessions.ts  # Gerenciamento de sessões
    │   │   ├── useIndexingProgress.ts # WebSocket progresso
    │   │   └── useTheme.ts     # Modo claro/escuro
    │   └── lib/api.ts          # Cliente HTTP centralizado
    └── nginx.conf              # Proxy reverso para /api/*
```

---

## 5. Backend

### 5.1 Configuração

Todas as configurações são lidas de variáveis de ambiente (ou arquivo `.env`) via `pydantic-settings`. A classe `Settings` (`app/core/config.py`) define os seguintes parâmetros:

| Variável | Descrição | Padrão |
|----------|-----------|--------|
| `DATABASE_URL` | URL de conexão asyncpg do PostgreSQL | — obrigatório |
| `QDRANT_URL` | URL da instância Qdrant | — obrigatório |
| `QDRANT_API_KEY` | Chave de API do Qdrant | — obrigatório |
| `OLLAMA_BASE_URL` | URL base do servidor Ollama | — obrigatório |
| `SECRET_KEY` | Chave JWT (mínimo 32 chars) | — obrigatório |
| `ALGORITHM` | Algoritmo JWT | `HS256` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Expiração do access token | `60` |
| `REFRESH_TOKEN_EXPIRE_DAYS` | Expiração do refresh token | `7` |
| `ALLOWED_ORIGINS` | CORS origins (separados por vírgula) | `http://localhost:3000` |
| `RERANKER_MODEL` | Modelo de reranking | `BAAI/bge-reranker-v2-m3` |
| `RERANKER_TOP_K` | Máximo de resultados após reranking | `5` |
| `RERANKER_SCORE_THRESHOLD` | Score mínimo pós-reranking | `0.5` |
| `HYDE_TEMPERATURE` | Temperatura para geração HyDE | `0.3` |
| `MULTIQUERY_COUNT` | Número de reformulações multi-query | `2` |
| `MULTIQUERY_TEMPERATURE` | Temperatura para multi-query | `0.3` |
| `CONTEXTUAL_COMPRESSION_ENABLED` | Habilitar compressão contextual | `true` |
| `CONTEXTUAL_COMPRESSION_TEMPERATURE` | Temperatura para compressão | `0.1` |

A instância `Settings` é um singleton via `@lru_cache` (`get_settings()`).

---

### 5.2 API REST

#### Autenticação — `/auth`

| Método | Rota | Descrição | Auth |
|--------|------|-----------|------|
| `POST` | `/auth/login` | Retorna access + refresh tokens JWT | Pública |

**Request body:**
```json
{ "email": "admin@ufpi.br", "password": "senha" }
```

**Response:**
```json
{ "access_token": "...", "refresh_token": "...", "token_type": "bearer" }
```

---

#### Documentos — `/documents`

| Método | Rota | Descrição | Auth |
|--------|------|-----------|------|
| `POST` | `/documents/upload` | Upload de PDF (inicia ingestão em background) | Admin |
| `GET` | `/documents/` | Lista documentos com paginação | Admin |
| `GET` | `/documents/{id}` | Detalhes de um documento | Admin |
| `DELETE` | `/documents/{id}` | Remove documento do PostgreSQL e Qdrant | Admin |
| `POST` | `/documents/reindex` | Reindexação total ou parcial | Admin |
| `POST` | `/documents/search` | Busca híbrida com reranking | Admin |
| `GET` | `/documents/stats` | Estatísticas da base (total, ativos, erros) | Admin |

**Upload — validações de segurança:**
- `Content-Type` deve ser `application/pdf` (MIME allowlist)
- Magic bytes verificados (`%PDF`)
- Tamanho máximo: 50 MB
- Nome de arquivo sanitizado (path traversal, null bytes, chars especiais)
- SHA-256 calculado para deduplicação

---

#### Chat — `/chat`

| Método | Rota | Descrição | Auth |
|--------|------|-----------|------|
| `POST` | `/chat/sessions` | Cria sessão (anônima ou autenticada) | Opcional |
| `POST` | `/chat/stream` | Streaming RAG via SSE | Pública |
| `GET` | `/chat/sessions` | Lista sessões do usuário | Opcional |
| `GET` | `/chat/sessions/{id}/messages` | Histórico de mensagens | Opcional |
| `DELETE` | `/chat/sessions/{id}` | Deleta sessão e mensagens | Opcional |
| `POST` | `/chat/messages/{id}/feedback` | Feedback em mensagem (👍/👎) | Opcional |

**Eventos SSE do endpoint `/chat/stream`:**

| Evento | Dados |
|--------|-------|
| `token` | Fragmento de texto gerado pelo LLM |
| `sources` | Array JSON com as fontes utilizadas |
| `done` | `"[DONE]"` — sinaliza fim do streaming |

---

#### Admin — `/admin`

| Método | Rota | Descrição | Auth |
|--------|------|-----------|------|
| `GET` | `/admin/rag-parameters` | Lê parâmetros RAG atuais | Admin |
| `PUT` | `/admin/rag-parameters` | Atualiza parâmetros RAG | Admin |

Parâmetros configuráveis: `parent_chunk_tokens`, `child_chunk_tokens`, `search_top_k`, `search_score_threshold`, `reranker_top_k`, `reranker_score_threshold`.

---

#### Avaliação — `/evaluation`

| Método | Rota | Descrição | Auth |
|--------|------|-----------|------|
| `POST` | `/evaluation/run` | Executa avaliação RAGAS (síncrono, pode demorar minutos) | Admin |
| `GET` | `/evaluation/results` | Lista histórico de avaliações | Admin |

---

#### Health Check

| Método | Rota | Descrição |
|--------|------|-----------|
| `GET` | `/health` | Retorna `{"status": "ok"}` |

---

### 5.3 Autenticação e Autorização

O sistema usa **JWT stateless** com dois tokens:

- **Access token**: expiração configurável (padrão 60 min), carrega `sub` (e-mail) e `role`
- **Refresh token**: expiração configurável (padrão 7 dias)

**Roles:**
- `admin` — acesso ao painel administrativo
- `superadmin` — mesmo acesso que admin

**Proteção contra enumeração de usuários (CWE-208):**  
O endpoint de login sempre executa o hash bcrypt, mesmo quando o e-mail não existe, garantindo tempo de resposta constante independente de o usuário existir ou não.

**Dependências FastAPI:**
- `get_current_user` — valida JWT e retorna usuário; levanta 401 se inválido
- `require_admin` — chama `get_current_user` e verifica role; levanta 403 se insuficiente
- `_optional_user_id` — retorna `None` para requisições anônimas sem erro

---

### 5.4 Pipeline RAG

O pipeline completo é implementado em `app/core/rag_engine.py` como gerador assíncrono `rag_stream()`, que produz eventos SSE.

```
Consulta do usuário
        │
        ▼
1. Normalização (whitespace)
        │
        ▼
2. HyDE — gera documento hipotético via Ollama (temperature 0.3)
        │
        ▼
3. Multi-query — MULTIQUERY_COUNT reformulações da query original
        │
        ▼ (union + deduplicação por ID Qdrant)
4. Busca híbrida para cada query reformulada
   ├── Dense: bge-m3 via Ollama /api/embed
   └── Sparse: BM42 via fastembed
   Fusão RRF (Reciprocal Rank Fusion) no Qdrant
        │
        ▼
5. Reranking — bge-reranker-v2-m3 via sentence-transformers
   Filtragem por score_threshold
        │
        ▼
6. Guard de fallback — se nenhum chunk sobreviver ao threshold:
   retorna mensagem padrão de "não possuo informações"
        │
        ▼
7. Expansão para chunks pai (expand_to_parents) — top-5
   + Compressão contextual (se CONTEXTUAL_COMPRESSION_ENABLED)
   + Histórico da conversa (PostgreSQL)
        │
        ▼
8. Montagem do prompt com template institucional PROPESQI
        │
        ▼
9. Streaming via Ollama /api/chat (gemma3:12b)
   Emite eventos SSE: token, sources, done
        │
        ▼
10. Persistência — salva mensagem do usuário + resposta no PostgreSQL
    Atualiza last_activity da sessão
```

**Prompt do sistema:**  
Define o assistente como funcionário virtual da PROPESQI/UFPI. Regras obrigatórias incluem: responder apenas com base nos documentos fornecidos no contexto, nunca inventar dados, sempre citar as fontes ao final, manter tom institucional em português formal.

---

### 5.5 Ingestão de Documentos

`app/ingestion/processor.py` — executado como `BackgroundTask` após upload.

**Ciclo de vida do documento:**
```
uploaded → processing → active  (sucesso)
uploaded → processing → error   (falha)
```

**Etapas:**

1. **Extração de texto** — tenta extração nativa (`pdfplumber`/`pypdf`). Se o PDF for digitalizado (pouco texto extraído), executa OCR com OpenCV + Tesseract
2. **Chunking hierárquico** (`app/ingestion/chunker.py`) — divide o texto em chunks pai e filho usando tiktoken `cl100k_base`. Tamanhos configuráveis via `rag_config` no banco
3. **Embedding denso** — chamadas em batch ao Ollama `/api/embed` com modelo `bge-m3` (batch de 32)
4. **Embedding esparso** — BM42 via `fastembed` (`app/ingestion/sparse.py`)
5. **Indexação no Qdrant** — upsert em batches de 100 `PointStruct` com vetores nomeados `{"dense": ..., "sparse": ...}`
6. **Registro no PostgreSQL** — cada chunk é registrado na tabela `chunks` (com `qdrant_id` e `text_preview`)
7. **Publicação de progresso** — eventos enviados ao pub/sub em memória (`app/core/progress.py`) para o WebSocket

---

### 5.6 Busca Híbrida

`app/db/search.py` — `hybrid_search(query, top_k, score_threshold, payload_filter)`

1. Gera vetor denso via Ollama (`bge-m3`)
2. Gera vetor esparso via BM42 (`fastembed`)
3. Executa `query_points` no Qdrant com dois `Prefetch` (dense + sparse) e fusão `FusionQuery(fusion=Fusion.RRF)`

`expand_to_parents(points)` — dado um conjunto de chunks filho retornados, agrupa por `parent_id` e retorna o texto do pai com metadados, eliminando redundâncias.

---

### 5.7 Reranking

`app/db/reranker.py` — `rerank(query, points, top_k, score_threshold)`

Utiliza `sentence-transformers` com o modelo `BAAI/bge-reranker-v2-m3` (carregado em CPU). Recalcula a relevância de cada chunk em relação à query original e filtra por threshold de score configurável. O modelo é iniciado uma única vez e reutilizado entre requisições.

---

### 5.8 Avaliação (RAGAS)

O módulo `app/core/evaluator.py` reproduz as etapas 2–8 do pipeline RAG de forma não-streaming e sem efeitos colaterais no banco de chat, permitindo medir qualidade de forma isolada.

**Métricas calculadas pelo RAGAS:**
- `faithfulness` — fidelidade ao contexto recuperado
- `answer_relevancy` — relevância da resposta à pergunta
- `context_precision` — precisão dos chunks recuperados
- `context_recall` — cobertura dos chunks em relação ao ground truth
- `answer_correctness` — correção da resposta vs. ground truth

Resultados são armazenados na tabela `rag_evaluations` no PostgreSQL.

---

### 5.9 WebSocket — Progresso de Indexação

**Rota:** `GET /ws/documents/{doc_id}/progress?token=<jwt>`

- JWT é passado como query parameter (browsers não suportam header `Authorization` em WebSocket)
- Role obrigatória: `admin` ou `superadmin`
- `doc_id` é validado como UUID para prevenir DoS por chaves arbitrárias
- Eventos são publicados pelo `processor.py` via `publish()` e entregues ao cliente via `subscribe()` (asyncio.Queue com maxsize=128)
- A conexão encerra automaticamente ao receber evento com `step = "done"` ou `step = "error"`

---

## 6. Banco de Dados

### 6.1 PostgreSQL — Esquema Relacional

#### `documents`
| Coluna | Tipo | Descrição |
|--------|------|-----------|
| `id` | `UUID PK` | Identificador único |
| `filename` | `TEXT` | Nome sanitizado no armazenamento |
| `original_name` | `TEXT` | Nome original do upload |
| `file_hash` | `TEXT UNIQUE` | SHA-256 para deduplicação |
| `file_type` | `TEXT` | `pdf_native`, `pdf_scanned`, `docx`, `odt`, `txt`, `md` |
| `ocr_applied` | `BOOLEAN` | Indica se OCR foi necessário |
| `status` | `TEXT` | `uploaded → processing → active/error` |
| `error_message` | `TEXT` | Detalhe do erro, se houver |
| `retry_count` | `INTEGER` | Contador de tentativas (máximo 3) |
| `total_chunks` | `INTEGER` | Quantidade de chunks indexados |
| `created_at` | `TIMESTAMPTZ` | Data de upload |
| `updated_at` | `TIMESTAMPTZ` | Última atualização |

#### `chunks`
| Coluna | Tipo | Descrição |
|--------|------|-----------|
| `id` | `UUID PK` | Identificador único |
| `document_id` | `UUID FK` | Referência ao documento pai |
| `qdrant_id` | `UUID UNIQUE` | ID do ponto no Qdrant |
| `page_number` | `INTEGER` | Número da página de origem |
| `chunk_index` | `INTEGER` | Índice sequencial do chunk |
| `text_preview` | `TEXT` | Primeiros 200 caracteres (exibição na UI) |
| `created_at` | `TIMESTAMPTZ` | Data de criação |

#### `chat_sessions`
| Coluna | Tipo | Descrição |
|--------|------|-----------|
| `id` | `UUID PK` | Identificador de sessão |
| `user_id` | `UUID` | `NULL` para usuários anônimos |
| `created_at` | `TIMESTAMPTZ` | Início da sessão |
| `last_activity` | `TIMESTAMPTZ` | Última mensagem |

#### `chat_messages`
| Coluna | Tipo | Descrição |
|--------|------|-----------|
| `id` | `UUID PK` | Identificador da mensagem |
| `session_id` | `UUID FK` | Sessão de origem |
| `role` | `TEXT` | `user` ou `assistant` |
| `content` | `TEXT` | Conteúdo da mensagem |
| `sources` | `JSONB` | Array de fontes: `[{"doc_id":"...","page":3,"score":0.87}]` |
| `feedback` | `TEXT` | `positive`, `negative` ou `NULL` |
| `created_at` | `TIMESTAMPTZ` | Timestamp da mensagem |

#### `users`
| Coluna | Tipo | Descrição |
|--------|------|-----------|
| `id` | `UUID PK` | Identificador |
| `email` | `TEXT UNIQUE` | E-mail institucional |
| `password_hash` | `TEXT` | Hash bcrypt |
| `role` | `TEXT` | `admin` ou `superadmin` |
| `created_at` | `TIMESTAMPTZ` | Data de criação |

#### `rag_config`
Tabela singleton com os parâmetros dinâmicos do pipeline RAG, atualizáveis sem reiniciar o serviço via `PUT /admin/rag-parameters`.

#### `rag_evaluations`
Histórico de execuções de avaliação RAGAS com métricas agregadas por run.

---

### 6.2 Qdrant — Coleção de Vetores

**Nome da coleção:** `propesqi_docs`

**Configuração de vetores:**
```python
vectors_config = {
    "dense": VectorParams(size=1024, distance=Distance.COSINE)
}
sparse_vectors_config = {
    "sparse": SparseVectorParams(modifier=Modifier.IDF)
}
```

**Payload de cada ponto:**
```json
{
  "doc_id": "uuid",
  "source": "nome_do_arquivo.pdf",
  "display_name": "Nome de Exibição",
  "page_number": 3,
  "chunk_index": 12,
  "parent_id": "uuid-do-chunk-pai",
  "parent_text": "texto completo do chunk pai",
  "text": "texto do chunk filho",
  "text_preview": "primeiros 200 chars...",
  "created_at": "2025-01-01T00:00:00Z"
}
```

A coleção é criada automaticamente na inicialização via `ensure_collection()` (chamada no `lifespan` do FastAPI). Se uma coleção incompatível existir (config antiga), ela é deletada e recriada.

---

## 7. Frontend

Aplicação SPA em React 18 + TypeScript + Vite, servida via Nginx.

**Views:**
- `chat` — interface pública de conversa
- `admin-login` — formulário de autenticação
- `admin` — painel de administração (protegido)

**Principais hooks:**

| Hook | Responsabilidade |
|------|-----------------|
| `useAuth` | Login, logout, estado do token JWT |
| `useChat` | Envio de mensagens, consumo do stream SSE, histórico |
| `useSessions` | Criação, listagem e remoção de sessões |
| `useIndexingProgress` | WebSocket para acompanhar progresso de indexação |
| `useTheme` | Alternância modo claro/escuro |

**Auto-logout:** Um event listener global em `App.tsx` captura o evento customizado `propesqi:auth-error` (disparado quando qualquer chamada autenticada recebe HTTP 401) e redireciona o usuário para a tela de login, sem exigir tratamento individual em cada hook.

**Nginx** serve os arquivos estáticos e faz proxy de `/api/*` para o backend.

---

## 8. Modelos de IA

| Modelo | Papel | VRAM |
|--------|-------|------|
| `gemma3:12b` | LLM principal — geração de respostas | ~8 GB (Q4_K_M) |
| `bge-m3` (BAAI) | Embeddings densos (1024 dims) | ~1,1 GB |
| `bge-reranker-v2-m3` (BAAI) | Reranking de chunks | CPU |
| `BM42` (fastembed) | Embeddings esparsos | CPU |

**Estratégia de VRAM (16 GB):**  
Com `OLLAMA_MAX_LOADED_MODELS=2`, o gemma3:12b e o bge-m3 permanecem carregados simultaneamente (~9 GB total), deixando margem para KV-cache e operações concorrentes. `OLLAMA_NUM_PARALLEL=1` serializa inferências para evitar thrashing de GPU.

---

## 9. Segurança

| Controle | Implementação |
|----------|---------------|
| Autenticação | JWT HS256 com expiração curta (access) + longa (refresh) |
| Senhas | bcrypt com salt aleatório via passlib |
| Timing attacks | Hash bcrypt executado mesmo para usuários inexistentes (CWE-208) |
| CORS | Allowlist explícita de origins via `ALLOWED_ORIGINS` |
| Upload | MIME allowlist, verificação de magic bytes, limite de tamanho |
| Path traversal | `Path(raw).name` antes de salvar arquivo (CWE-22) |
| Null bytes | Stripped do nome do arquivo antes do processamento (CWE-626) |
| WebSocket DoS | `doc_id` validado como UUID antes de criar subscriber |
| QDRANT | API key obrigatória; não exposta externamente |
| Secrets | `SECRET_KEY` mínimo 32 chars, validado na inicialização |
| Role-based access | `admin`/`superadmin` para todas as rotas administrativas |

---

## 10. Implantação com Docker

### Serviços

| Serviço | Imagem | Porta interna |
|---------|--------|--------------|
| `postgres` | `postgres:16-alpine` | 5432 |
| `qdrant` | `qdrant/qdrant:latest` | 6333 (REST), 6334 (gRPC) |
| `ollama` | `ollama/ollama` | 11434 |
| `backend` | Build local (`backend/Dockerfile`) | 8000 |
| `frontend` | Build local (`frontend/Dockerfile`) | 80 |

Todos os serviços se comunicam pela rede Docker interna `propesqi-net`. O PostgreSQL é o único com porta exposta ao host (5432) para acesso de ferramentas de administração.

### Inicialização do banco

Os scripts em `init/` são executados pelo container do PostgreSQL na primeira inicialização:
1. `00_roles.sh` — cria role de aplicação com privilégios mínimos
2. `01_schema.sql` — cria todas as tabelas, índices e extensões (idempotente via `CREATE ... IF NOT EXISTS`)

### Subir com GPU (NVIDIA)

```bash
# Pré-requisito: nvidia-container-toolkit instalado no host
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d
```

### Subir sem GPU (CPU)

```bash
docker compose up -d
```

### Baixar modelos no Ollama

```bash
docker exec propesqi_ollama ollama pull gemma3:12b
docker exec propesqi_ollama ollama pull bge-m3
```

---

## 11. Variáveis de Ambiente

Crie um arquivo `.env` na raiz do projeto:

```env
# PostgreSQL
POSTGRES_USER=propesqi_admin
POSTGRES_PASSWORD=<senha-forte>
POSTGRES_DB=propesqi
PROPESQI_APP_PASSWORD=<senha-role-app>

# Conexão da aplicação (role limitada)
DATABASE_URL=postgresql+asyncpg://propesqi_app:<PROPESQI_APP_PASSWORD>@postgres:5432/propesqi

# Qdrant
QDRANT_URL=http://qdrant:6333
QDRANT_API_KEY=<chave-aleatória>

# Ollama
OLLAMA_BASE_URL=http://ollama:11434

# JWT — gere com: python3 -c "import secrets; print(secrets.token_hex(32))"
SECRET_KEY=<mínimo-32-chars>

# CORS (produção: URL do frontend)
ALLOWED_ORIGINS=http://localhost:3000
```

---

## 12. Testes

```
backend/tests/
├── conftest.py                 # Fixtures compartilhadas (AsyncClient, DB)
├── test_document_names.py      # Testes unitários de normalização de nomes
├── test_rag_engine.py          # Testes unitários do pipeline RAG
├── latency/
│   ├── test_auth.py            # Teste de latência do endpoint de login
│   ├── test_chat_stream.py     # Teste de latência do streaming RAG
│   ├── test_health.py          # Teste de latência do health check
│   └── test_search.py          # Teste de latência da busca
└── load/
    └── locustfile.py           # Cenários de carga com Locust
```

### Executar testes unitários

```bash
cd backend
pytest tests/ -v --ignore=tests/latency --ignore=tests/load
```

### Executar testes de carga

```bash
cd backend
locust -f tests/load/locustfile.py --host=http://localhost:8000
```
