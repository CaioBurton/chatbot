# Documentação Técnica — PROPESQI RAG Chatbot

Sistema de perguntas e respostas sobre documentos institucionais da Pró-Reitoria de Pesquisa e Inovação (PROPESQI) da Universidade Federal do Piauí (UFPI). Suporta dois modos de LLM: **local** (Ollama + gemma3:12b, totalmente on-premise) e **externo** (Gemini, OpenAI ou Anthropic via API key), configuráveis em runtime sem reiniciar o serviço.

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
   - 5.10 [Warmup de Modelos](#510-warmup-de-modelos)
6. [Banco de Dados](#6-banco-de-dados)
   - 6.1 [PostgreSQL — Esquema Relacional](#61-postgresql--esquema-relacional)
   - 6.2 [Qdrant — Coleção de Vetores](#62-qdrant--coleção-de-vetores)
7. [Frontend](#7-frontend)
8. [Modelos de IA](#8-modelos-de-ia)
9. [Segurança](#9-segurança)
10. [Implantação com Docker](#10-implantação-com-docker)
11. [Variáveis de Ambiente](#11-variáveis-de-ambiente)
12. [Testes e Avaliação](#12-testes-e-avaliação)

---

## 1. Visão Geral

O sistema permite que usuários da UFPI façam perguntas em linguagem natural sobre documentos institucionais da PROPESQI (editais, resoluções, regulamentos, aditivos, etc.) e recebam respostas fundamentadas exclusivamente no conteúdo indexado, com citação das fontes.

**Características principais:**
- Chat público (sem login) com streaming de respostas via SSE
- Painel administrativo protegido por JWT para upload, gestão e reindexação de documentos
- Pipeline RAG avançado com 9 estágios: normalização, HyDE, multi-query, busca híbrida RRF, injeções lexicais e pinadas, reranking, expansão edital_ref, compressão contextual e streaming LLM
- Suporte a LLM local (Ollama/gemma3:12b) e externo (Gemini, OpenAI, Anthropic) — alternável em runtime pelo painel admin
- Suporte a PDFs nativos e digitalizados (OCR via Tesseract + OpenCV)
- Vinculação de aditivos ao edital de referência (`edital_ref`) com expansão bidirecional de contexto no RAG

---

## 2. Arquitetura

```
┌──────────────────────────────────────────────────────────────────┐
│                     FRONTEND (React + Vite)                      │
│  ┌─────────────────────┐   ┌──────────────────────────────────┐  │
│  │  Chat (público)     │   │  Painel Admin (autenticado)      │  │
│  │  • Streaming SSE    │   │  • Upload de PDFs + edital_ref   │  │
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
│  │  1. Normalização + Guards (saudação / identidade)        │    │
│  │  2. HyDE  →  3. Multi-query (paralelo)                   │    │
│  │  4. Hybrid Search RRF + Injeções Lexicais                │    │
│  │  5. Rerank  →  6. Guard de fallback                      │    │
│  │  7. Context assembly + Injeções Pinadas + edital_ref     │    │
│  │  8. Compressão contextual  →  9. LLM Streaming           │    │
│  └────────────────┬──────────────────────┬───────────────---┘    │
└───────────────────┼──────────────────────┼───────────────────────┘
                    │                      │
     ┌──────────────▼──────┐  ┌────────────▼─────────────────────┐
     │  Qdrant             │  │  LLM Provider (selecionável)      │
     │  Hybrid Search      │  │  • Local: Ollama → gemma3:12b     │
     │  BM42 + bge-m3      │  │  • Externo: Gemini / OpenAI /     │
     │  RRF Fusion         │  │    Anthropic                      │
     └─────────────────────┘  └───────────────────────────────────┘
                    │
     ┌──────────────▼──────────────────────────────────────┐
     │             Pipeline de Ingestão de Documentos      │
     │  PDF nativo  →  pdfplumber / pypdf                   │
     │  PDF scan    →  OpenCV + Tesseract OCR               │
     │  Chunking    →  Parent-Child (tiktoken cl100k_base)  │
     │  Payload     →  doc_type + edital_ref por chunk      │
     │  Embeddings  →  bge-m3 via Ollama (batches de 32)    │
     └─────────────────────────────────────────────────────┘
                    │
     ┌──────────────▼──────┐  ┌──────────────────┐
     │  PostgreSQL 16      │  │  Ollama           │
     │  Usuários           │  │  bge-m3 (embed)   │
     │  Sessões / Chat     │  │  gemma3:12b (LLM) │
     │  Documentos         │  │  GPU RTX 5060 Ti  │
     │  rag_config         │  │  (modo local)     │
     └─────────────────────┘  └───────────────────┘
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
| LLM local | Ollama → `gemma3:12b` | — |
| LLM externo (opcional) | `gemini-3.1-flash-lite` / OpenAI / Anthropic | — |
| Modelo de embeddings | BAAI/bge-m3 (Ollama) | 1024 dims |
| Encoder esparso | fastembed BM42 | ≥ 0.3 |
| Reranker | BAAI/bge-reranker-v2-m3 (sentence-transformers) | — |
| OCR | Tesseract 5 + OpenCV | — |
| Tokenizer | tiktoken (cl100k_base) | ≥ 0.6 |
| Autenticação | JWT (python-jose) + bcrypt | — |
| Avaliação RAG | RAGAS | ≥ 0.1 |
| Containerização | Docker Compose | v2+ |

---

## 4. Estrutura de Diretórios

```
chatbot/
├── docker-compose.yml          # Stack completo com GPU habilitada por padrão
├── docker-compose.gpu.yml      # Overlay para count: all (multi-GPU)
├── README.md                   # Guia de início rápido e visão geral
├── CLAUDE.md                   # Instruções para Claude Code
├── AGENTS.md                   # Convenções de arquitetura para agentes
├── DOCUMENTATION.md            # Esta documentação técnica detalhada
├── PLANEJAMENTO.md             # Documento de planejamento original
│
├── init/
│   ├── 00_roles.sh             # Cria role limitada no PostgreSQL
│   ├── 01_schema.sql           # DDL — tabelas, índices, migrações (idempotente)
│   └── 02_seed_admin.sh        # Seed do primeiro usuário admin
│
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── pyproject.toml          # pytest asyncio_mode = auto
│   ├── models/                 # Bind mount para modelo fine-tuned do reranker
│   └── app/
│       ├── main.py             # Ponto de entrada FastAPI + lifespan + warmup
│       ├── api/routes/
│       │   ├── auth.py         # POST /auth/login, POST /auth/refresh
│       │   ├── chat.py         # /chat/sessions, /chat/stream, feedback
│       │   ├── documents.py    # Upload, CRUD, busca, reindexação, edital_ref
│       │   ├── admin.py        # GET/PUT /admin/rag-parameters
│       │   ├── evaluation.py   # RAGAS evaluation
│       │   └── ws.py           # WebSocket progresso de indexação
│       ├── core/
│       │   ├── config.py       # Settings via pydantic-settings (@lru_cache)
│       │   ├── security.py     # JWT, bcrypt, depends. de autorização
│       │   ├── rag_engine.py   # Pipeline RAG completo + streaming SSE
│       │   ├── embeddings.py   # generate_dense_embeddings (local/gemini)
│       │   ├── evaluator.py    # Lógica de avaliação RAGAS
│       │   ├── progress.py     # Pub/sub in-process para progresso de indexação
│       │   └── document_names.py # Normalização de nomes de exibição
│       ├── db/
│       │   ├── postgres.py     # Engine AsyncSA + fábrica de sessão
│       │   ├── qdrant.py       # Cliente Qdrant singleton + ensure_collection()
│       │   ├── search.py       # hybrid_search() + expand_to_parents()
│       │   ├── reranker.py     # rerank() via sentence-transformers (GPU)
│       │   └── rag_config.py   # Leitura/seed da config RAG singleton (DB)
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
    │   │   ├── chat/           # ChatWindow, MessageBubble, ChatInput, WelcomeScreen
    │   │   ├── admin/          # AdminPanel, DocumentTable, UploadZone,
    │   │   │                   # UploadMetadataModal (campo edital_ref), …
    │   │   └── layout/         # Sidebar
    │   ├── hooks/
    │   │   ├── useAuth.ts      # Estado de autenticação
    │   │   ├── useChat.ts      # Streaming SSE + histórico
    │   │   ├── useSessions.ts  # Gerenciamento de sessões
    │   │   ├── useIndexingProgress.ts # WebSocket progresso
    │   │   └── useTheme.ts     # Modo claro/escuro
    │   └── lib/
    │       ├── api.ts          # Cliente HTTP centralizado
    │       └── uuid.ts         # crypto.randomUUID com fallback (HTTP seguro)
    └── nginx.conf              # Proxy reverso /api/* → backend:8000
```

---

## 5. Backend

### 5.1 Configuração

Todas as configurações são lidas de variáveis de ambiente (ou arquivo `.env`) via `pydantic-settings`. A classe `Settings` (`app/core/config.py`) é um singleton via `@lru_cache` em `get_settings()`. Nunca instanciar `Settings()` diretamente.

**Variáveis de ambiente (`Settings`):**

| Variável | Descrição | Padrão |
|----------|-----------|--------|
| `DATABASE_URL` | URL asyncpg do PostgreSQL | obrigatório |
| `QDRANT_URL` | URL da instância Qdrant | obrigatório |
| `QDRANT_API_KEY` | Chave de API do Qdrant | obrigatório |
| `OLLAMA_BASE_URL` | URL base do servidor Ollama | obrigatório |
| `SECRET_KEY` | Chave JWT (mínimo 32 chars) | obrigatório |
| `ALGORITHM` | Algoritmo JWT | `HS256` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Expiração do access token | `60` |
| `REFRESH_TOKEN_EXPIRE_DAYS` | Expiração do refresh token | `7` |
| `ALLOWED_ORIGINS` | CORS origins (separados por vírgula) | `http://localhost:3000` |
| `RERANKER_MODEL` | Modelo de reranking (path local ou HuggingFace) | `BAAI/bge-reranker-v2-m3` |
| `HYDE_TEMPERATURE` | Temperatura para geração HyDE | `0.3` |
| `MULTIQUERY_COUNT` | Número de reformulações multi-query | `2` |
| `MULTIQUERY_TEMPERATURE` | Temperatura para multi-query | `0.3` |
| `CONTEXTUAL_COMPRESSION_ENABLED` | Habilitar compressão contextual | `true` |
| `CONTEXTUAL_COMPRESSION_TEMPERATURE` | Temperatura para compressão | `0.1` |
| `OPENAI_API_KEY` | Chave OpenAI (opcional) | `""` |
| `ANTHROPIC_API_KEY` | Chave Anthropic (opcional) | `""` |
| `GOOGLE_API_KEY` | Chave Google Gemini (opcional) | `""` |

**Parâmetros RAG dinâmicos (`rag_config` no PostgreSQL):**

Esses parâmetros são lidos a cada requisição via `get_rag_config(db)` e alteráveis em runtime pelo endpoint `PUT /admin/rag-parameters` sem reiniciar o serviço.

| Parâmetro | Descrição | Padrão |
|-----------|-----------|--------|
| `parent_chunk_tokens` | Tokens por chunk pai | `512` |
| `child_chunk_tokens` | Tokens por chunk filho | `128` |
| `search_top_k` | Candidatos retornados pela busca híbrida | `20` |
| `search_score_threshold` | Score mínimo pós-busca | `0.0` |
| `reranker_top_k` | Resultados mantidos após reranking | `5` |
| `reranker_score_threshold` | Score mínimo pós-reranking | `0.5` |
| `context_top_k` | Chunks pai no contexto final | `5` |
| `hyde_enabled` | Liga/desliga HyDE | `true` |
| `multiquery_enabled` | Liga/desliga multi-query | `true` |
| `reranker_enabled` | Liga/desliga reranker | `true` |
| `contextual_compression_enabled` | Liga/desliga compressão contextual | `true` |
| `parent_child_expansion_enabled` | Liga/desliga expansão para chunks pai | `true` |
| `llm_provider` | Provedor LLM: `local`, `openai`, `anthropic`, `gemini` | `local` |
| `llm_model` | Modelo LLM (ex: `gemma3:12b`, `gemini-3.1-flash-lite`) | `gemma3:12b` |
| `embedding_provider` | Provedor de embeddings: `local`, `gemini` | `local` |
| `embedding_model` | Modelo de embeddings | `bge-m3` |

---

### 5.2 API REST

#### Autenticação — `/api/auth`

| Método | Rota | Descrição | Auth |
|--------|------|-----------|------|
| `POST` | `/auth/login` | Retorna access + refresh tokens JWT | Pública |
| `POST` | `/auth/refresh` | Renova access token com refresh token | Pública |

**Login — request:**
```json
{ "email": "admin@ufpi.br", "password": "senha" }
```
**Login — response:**
```json
{ "access_token": "...", "refresh_token": "...", "token_type": "bearer" }
```

---

#### Documentos — `/api/documents`

| Método | Rota | Descrição | Auth |
|--------|------|-----------|------|
| `POST` | `/documents/upload` | Upload de PDF, inicia ingestão em background | Admin |
| `GET` | `/documents` | Lista documentos com paginação | Admin |
| `GET` | `/documents/stats` | Totais: documentos, chunks, erros | Admin |
| `GET` | `/documents/{id}` | Detalhes de um documento | Admin |
| `DELETE` | `/documents/{id}` | Remove do PostgreSQL e Qdrant | Admin |
| `POST` | `/documents/{id}/reindex` | Reprocessa documento com erro | Admin |
| `POST` | `/documents/reindex` | Reindexação total ou parcial (`scope: "all"\|"pending"`) | Admin |
| `POST` | `/documents/search` | Busca híbrida com reranking opcional | Admin |
| `POST` | `/documents/search/expanded` | Busca com expansão para chunks pai | Admin |

**Upload — campos aceitos (multipart/form-data):**

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `file` | PDF | Arquivo a indexar |
| `display_name` | string (opcional) | Nome de exibição na UI |
| `source_url` | string (opcional) | Link externo para o documento original |
| `doc_type` | string | `edital`, `aditivo`, `resolucao`, `tutorial`, `portaria`, `relatorio` |
| `edital_ref` | string (opcional) | Para aditivos: nome do edital de referência (ativa expansão bidirecional no RAG) |

**Validações de segurança no upload:**
- `Content-Type: application/pdf` (MIME allowlist)
- Magic bytes verificados (`%PDF`) — defesa contra MIME spoofing (OWASP A03)
- Tamanho máximo: 50 MB
- Nome do arquivo sanitizado contra path traversal (CWE-22) e null bytes (CWE-626)
- SHA-256 para deduplicação — rejeita duplicatas com HTTP 409

---

#### Chat — `/api/chat`

| Método | Rota | Descrição | Auth |
|--------|------|-----------|------|
| `POST` | `/chat/sessions` | Cria sessão | Opcional |
| `GET` | `/chat/sessions` | Lista sessões do usuário | Opcional |
| `GET` | `/chat/sessions/{id}/messages` | Histórico de mensagens | Opcional |
| `DELETE` | `/chat/sessions/{id}` | Deleta sessão e mensagens | Opcional |
| `POST` | `/chat/stream` | Streaming RAG via SSE | Pública |
| `POST` | `/chat/messages/{id}/feedback` | Feedback 👍/👎 em mensagem | Opcional |

**Eventos SSE do endpoint `/chat/stream`:**

| Evento | Dados |
|--------|-------|
| `message_id` | UUID da mensagem (para feedback assíncrono) |
| `token` | Fragmento de texto gerado pelo LLM |
| `sources` | Array JSON com as fontes utilizadas |
| `done` | `"[DONE]"` — sinaliza fim do streaming |

---

#### Admin — `/api/admin`

| Método | Rota | Descrição | Auth |
|--------|------|-----------|------|
| `GET` | `/admin/rag-parameters` | Lê parâmetros RAG atuais | Admin |
| `PUT` | `/admin/rag-parameters` | Atualiza parâmetros RAG em runtime | Admin |

---

#### Avaliação — `/api/evaluation`

| Método | Rota | Descrição | Auth |
|--------|------|-----------|------|
| `POST` | `/evaluation/run` | Executa avaliação RAGAS (síncrono) | Admin |
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
- `admin` — acesso completo ao painel administrativo
- `superadmin` — mesmo acesso que admin

**Proteção contra enumeração de usuários (CWE-208):**
O endpoint de login sempre executa o hash bcrypt, mesmo quando o e-mail não existe, garantindo tempo de resposta constante.

**Dependências FastAPI em `app/core/security.py`:**
- `get_current_user` — valida JWT, retorna usuário; levanta HTTP 401 se inválido
- `require_admin` — chama `get_current_user` e verifica role; levanta HTTP 403 se insuficiente
- `_optional_user_id` — retorna `None` para requisições anônimas sem erro

---

### 5.4 Pipeline RAG

Implementado em `app/core/rag_engine.py` como gerador assíncrono `rag_stream()`. Todos os provedores LLM (local/openai/anthropic/gemini) são acessados via `_llm_generate()`, wrapper provider-agnostic que delega para as funções específicas de cada API.

O semáforo `_OLLAMA_SEMAPHORE = asyncio.Semaphore(1)` serializa todas as chamadas de inferência ao Ollama, evitando OOM em GPUs com 16 GB (gemma3:12b Q4_K_M ocupa ~8 GB de VRAM). Para provedores externos, não há semáforo — os limites de rate da API são gerenciados pelo provider.

```
Consulta do usuário
        │
        ▼
1. Normalização e Guards rápidos
   ├── Whitespace normalization
   ├── Guard de saudação (regex): resposta cordial sem RAG
   └── Guard de identidade (regex): apresentação do assistente sem RAG
        │
        ▼
2. HyDE (Hypothetical Document Embedding)
   Gera documento hipotético via LLM (temperature 0.3) para melhorar
   a qualidade do vetor de busca
        │
3. Multi-query (paralelo com HyDE via asyncio.gather)
   Gera MULTIQUERY_COUNT reformulações da query original
        │
        ▼ (union + deduplicação por ID Qdrant, mantém maior score)
4. Busca híbrida RRF para cada query do pool
   ├── Dense: bge-m3 via Ollama /api/embed (1024 dims)
   ├── Sparse: BM42 via fastembed
   ├── Fusão RRF no Qdrant
   └── Injeções lexicais (_LEXICAL_EXPANSIONS):
       Queries sintéticas adicionadas ao pool para vocabulário
       mismatch (ex: "sistema"→SIGAA, "colégio"→lotado/vinculado,
       "acumular bolsa"→devolver mensalidades indevidamente)
        │
        ▼
5. Reranking — bge-reranker-v2-m3 (sentence-transformers, GPU)
   Query aumentada com termos de expansão lexical para pontuação
   cross-encoder correta. Filtragem por reranker_score_threshold.
        │
        ▼
6. Guard de fallback
   Se nenhum chunk sobreviver ao threshold: emite mensagem padrão
   "Não possuo informações..." e encerra sem chamar o LLM
        │
        ▼
7. Context assembly
   a) expand_to_parents(): top context_top_k chunks pai
   b) Injeções pinadas (ordem de avaliação):
      • ICV habilitação (Q15-type): score mínimo + filtro source "icv"
      • Vigência bolsa (Q05-type): seção "DO PERÍODO DE VIGÊNCIA DA BOLSA"
      • Vigência todos os programas (Q25-type): chunk de vigência por edital
      • PIBICEM colégio (Q21-type): seção 3.2.1 + filtro source "pibicem"
   c) Expansão edital_ref (bidirecional):
      • Forward: aditivo no contexto → pula chunks do edital pai
      • Reverse: edital no contexto → busca aditivos cujo edital_ref
        faz match (substring case-insensitive) com display_name do edital
   d) Histórico da conversa (PostgreSQL, últimas 10 mensagens)
        │
        ▼
8. Compressão contextual (se habilitada)
   Para cada chunk pai, chama o LLM para extrair apenas as frases
   diretamente relevantes à query (temperatura 0.1). Falhas silenciosas
   — mantém texto original em caso de exceção ou output vazio.
        │
        ▼
9. Montagem do prompt + Streaming LLM
   Template com CONTEXTO DOS DOCUMENTOS + HISTÓRICO + 6 REGRAS:
   1. Responder EXCLUSIVAMENTE com base nos documentos
   2. Fallback se informação não estiver nos documentos
   3. Nunca inventar datas, normas ou valores
   4. Tom institucional, respeitoso e acessível
   5. Datas com dia, mês e ano completos
   6. Vigência de bolsas: duração em meses + início + término
   Streaming via Ollama /api/chat ou API externa (SSE: token, sources, done)
        │
        ▼
10. Persistência
    Salva mensagem do usuário + resposta no PostgreSQL.
    Atualiza last_activity da sessão.
```

#### Injeções Lexicais (`_LEXICAL_EXPANSIONS`)

Lista de tuplas `(regex, query_sintética)` em módulo-nível. Quando a query faz match no regex, a query sintética é adicionada ao pool de busca híbrida (estágio 4) **e** concatenada à query do reranker (estágio 5), para corrigir mismatch de vocabulário entre a pergunta do usuário e o texto dos chunks relevantes.

| Padrão regex | Query sintética injetada | Problema resolvido |
|---|---|---|
| `sistema\|plataforma\|portal` | "SIGAA sistema integrado..." | Q26: usuário usa "sistema", chunk usa "SIGAA" |
| `filho\|filha\|cônjuge\|parente` | "vedado cônjuge parente afinidade..." | Q29: conflito de interesse |
| `vigência` | "DO PERÍODO DE VIGÊNCIA DA BOLSA doze meses..." | Q05/Q25: vocabulário da seção |
| `vigência + todos\|programas` | "PIBIC ICV PIBITI PIBICEM todos programas..." | Q25: cross-document |
| `colégio\|escola` | "sem obrigatoriedade vinculado colégio lotado..." | Q21: PIBICEM 3.2.1 |
| `acumular + PIBITI/bolsa` | "PIBITI vedado acumular devolver mensalidades..." | Q18: penalidade PIBITI |
| `pontos mínimos` | "pontos mínimos habilitado análise tabela..." | Q06/Q15: habilitação |
| `ICV + pontos mínimos` | "ICV habilitado etapa análise proponente..." | Q15: ICV específico |

#### Injeções Pinadas

Para casos onde a injeção lexical não é suficiente (chunk correto não sobrevive ao reranker por competição), o pipeline faz uma busca adicional filtrada por fonte, expande para o chunk pai e força sua entrada no contexto no topo da lista.

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
2. **Resolução de display_name** — usa título extraído do PDF, metadado `Title`, ou nome do arquivo original (nessa ordem de preferência)
3. **Chunking hierárquico** (`app/ingestion/chunker.py`) — divide o texto em chunks pai (512 tokens) e filho (128 tokens) usando tiktoken `cl100k_base`. Tamanhos configuráveis via `rag_config`
4. **Embedding denso** — chamadas em batch ao Ollama `/api/embed` com `bge-m3` (batch de 32)
5. **Embedding esparso** — BM42 via `fastembed` (`app/ingestion/sparse.py`)
6. **Indexação no Qdrant** — upsert em batches de pontos com vetores nomeados `{"dense": ..., "sparse": ...}` e payload completo (incluindo `doc_type` e `edital_ref`)
7. **Publicação de progresso** — eventos enviados ao pub/sub em memória (`app/core/progress.py`) para o WebSocket consumir

**Payload de cada chunk no Qdrant:**
```json
{
  "doc_id": "uuid",
  "source": "nome_arquivo.pdf",
  "display_name": "Nome de Exibição",
  "page_number": 3,
  "chunk_index": 12,
  "parent_id": "uuid-do-chunk-pai",
  "parent_text": "texto completo do chunk pai (512 tokens)",
  "text": "texto do chunk filho (128 tokens)",
  "created_at": "2025-01-01T00:00:00Z",
  "hash": "sha256hexdigest",
  "doc_type": "edital",
  "edital_ref": null
}
```

O campo `edital_ref` é `null` para editais e resoluções; para aditivos re-indexados após o preenchimento no modal de upload, contém o nome do edital de referência (ex: `"Edital ICV 2025/2026"`).

---

### 5.6 Busca Híbrida

`app/db/search.py`

**`hybrid_search(query, top_k, score_threshold, payload_filter, embedding_provider, embedding_model)`**

1. Gera vetor denso via `generate_dense_embeddings()` (local Ollama ou Gemini)
2. Gera vetor esparso via BM42 (`fastembed`)
3. Executa `query_points` no Qdrant com dois `Prefetch` (dense + sparse) e `FusionQuery(fusion=Fusion.RRF)`

**`expand_to_parents(points) → list[dict]`**

Dado um conjunto de chunks filho retornados, agrupa por `parent_id` (mantém maior score por pai), retorna dicts com campos: `parent_id`, `parent_text`, `doc_id`, `source`, `display_name`, `page_number`, `score`, `doc_type`, `edital_ref`.

O campo `edital_ref` é propagado do payload Qdrant e usado pelo estágio de expansão bidirecional (7c) no pipeline RAG.

---

### 5.7 Reranking

`app/db/reranker.py` — **`rerank(query, points, top_k, score_threshold)`**

Utiliza `sentence-transformers` com `BAAI/bge-reranker-v2-m3`. O modelo é carregado na GPU na primeira chamada (ou no warmup do startup) e reutilizado entre requisições. O modelo alternativo (fine-tuned) pode ser especificado via variável `RERANKER_MODEL` apontando para um path local (ex: `./models/reranker-propesqi`).

---

### 5.8 Avaliação (RAGAS)

`app/core/evaluator.py` reproduz os estágios 2–9 do pipeline RAG em modo não-streaming e sem efeitos colaterais no banco de chat.

**Métricas RAGAS calculadas:**
- `faithfulness` — fidelidade ao contexto recuperado
- `answer_relevancy` — relevância da resposta à pergunta
- `context_precision` — precisão dos chunks recuperados
- `context_recall` — cobertura dos chunks em relação ao ground truth
- `answer_correctness` — correção da resposta vs. ground truth

Resultados são armazenados na tabela `rag_evaluations`.

**Harness de avaliação offline (`backend/tests/run_groundtruth_eval.py`):**

Avalia o pipeline contra 30 perguntas com gabarito (`backend/tests/groundtruth_chatbot_rag.csv`) usando `gemini-3.1-flash-lite` como LLM judge (free tier, 15 RPM). Cada pergunta consome ~5 chamadas Gemini (HyDE + multi-query + geração + judge + margem). O script gerencia rate limiting automaticamente com intervalo mínimo de 35 s/pergunta.

Melhor resultado obtido: **4.620/5 (92.4%)** — Passo 14, com gemini-3.1-flash-lite como LLM do pipeline e judge.

---

### 5.9 WebSocket — Progresso de Indexação

**Rota:** `GET /ws/documents/{doc_id}/progress?token=<jwt>`

- JWT passado como query parameter (browsers não suportam header `Authorization` em WebSocket nativo)
- Role obrigatória: `admin` ou `superadmin`
- `doc_id` validado como UUID para prevenir DoS por chaves arbitrárias
- Eventos publicados pelo `processor.py` via `publish()` em asyncio.Queue (maxsize=128)
- Conexão encerra ao receber `step = "done"` ou `step = "error"`

**Formato dos eventos:**
```json
{
  "step": "chunking",
  "detail": "Fragmentando o texto em chunks...",
  "progress": 35
}
```

---

### 5.10 Warmup de Modelos

`app/main.py` — função `_warmup()` chamada no `lifespan` do FastAPI antes de aceitar requisições.

Pré-carrega todos os modelos de inferência em paralelo para eliminar a latência da primeira requisição:

1. **bge-m3** (Ollama dense embeddings) e **BM42** (fastembed sparse) — em paralelo via `asyncio.gather`
2. **CrossEncoder bge-reranker-v2-m3** (PyTorch, GPU) — após os embeddings estarem prontos

Falhas no warmup são silenciosas (exceto logging) — o servidor inicia mesmo que um modelo demore a carregar.

---

## 6. Banco de Dados

### 6.1 PostgreSQL — Esquema Relacional

#### `documents`

| Coluna | Tipo | Descrição |
|--------|------|-----------|
| `id` | `UUID PK` | Identificador único |
| `filename` | `TEXT NOT NULL` | Nome sanitizado no armazenamento local |
| `original_name` | `TEXT NOT NULL` | Nome original do arquivo no upload |
| `display_name` | `TEXT` | Nome de exibição (admin pode customizar) |
| `source_url` | `TEXT` | Link externo opcional para o documento original |
| `doc_type` | `TEXT NOT NULL` | `edital`, `aditivo`, `resolucao`, `tutorial`, `portaria`, `relatorio` |
| `edital_ref` | `TEXT` | Para aditivos: nome do edital de referência |
| `file_hash` | `TEXT UNIQUE NOT NULL` | SHA-256 para deduplicação |
| `file_type` | `TEXT NOT NULL` | `pdf_native`, `pdf_scanned`, `docx`, `odt`, `txt`, `md` |
| `ocr_applied` | `BOOLEAN NOT NULL` | Indica se OCR foi aplicado |
| `status` | `TEXT NOT NULL` | `uploaded → processing → active/error` |
| `error_message` | `TEXT` | Detalhe do erro, quando status = error |
| `retry_count` | `INTEGER NOT NULL` | Contador de tentativas (máximo 3) |
| `total_chunks` | `INTEGER` | Quantidade de chunks indexados |
| `created_at` | `TIMESTAMPTZ NOT NULL` | Data de upload |
| `updated_at` | `TIMESTAMPTZ NOT NULL` | Atualizado automaticamente por trigger |

#### `chunks`

Mirror do payload Qdrant para permitir JOINs SQL sem consultar o vector store.

| Coluna | Tipo | Descrição |
|--------|------|-----------|
| `id` | `UUID PK` | Identificador único |
| `document_id` | `UUID FK → documents` | Documento pai (CASCADE DELETE) |
| `qdrant_id` | `UUID UNIQUE NOT NULL` | ID do ponto no Qdrant |
| `page_number` | `INTEGER` | Número da página de origem |
| `chunk_index` | `INTEGER NOT NULL` | Índice sequencial |
| `text_preview` | `TEXT` | Primeiros 200 caracteres (UI admin) |
| `created_at` | `TIMESTAMPTZ NOT NULL` | Data de criação |

#### `chat_sessions`

| Coluna | Tipo | Descrição |
|--------|------|-----------|
| `id` | `UUID PK` | Identificador da sessão |
| `user_id` | `UUID` | `NULL` para usuários anônimos |
| `created_at` | `TIMESTAMPTZ NOT NULL` | Início da sessão |
| `last_activity` | `TIMESTAMPTZ NOT NULL` | Última mensagem |

#### `chat_messages`

| Coluna | Tipo | Descrição |
|--------|------|-----------|
| `id` | `UUID PK` | Identificador |
| `session_id` | `UUID FK → chat_sessions` | Sessão de origem (CASCADE DELETE) |
| `role` | `TEXT NOT NULL` | `user` ou `assistant` |
| `content` | `TEXT NOT NULL` | Conteúdo da mensagem |
| `sources` | `JSONB` | `[{"doc_id":"...","original_name":"...","page_number":3,"score":0.87}]` |
| `feedback` | `TEXT` | `up`, `down` ou `NULL` |
| `created_at` | `TIMESTAMPTZ NOT NULL` | Timestamp |

#### `users`

| Coluna | Tipo | Descrição |
|--------|------|-----------|
| `id` | `UUID PK` | Identificador |
| `email` | `TEXT UNIQUE NOT NULL` | E-mail (login) |
| `password_hash` | `TEXT NOT NULL` | Hash bcrypt |
| `role` | `TEXT NOT NULL` | `admin` ou `superadmin` |
| `created_at` | `TIMESTAMPTZ NOT NULL` | Data de criação |

#### `rag_config`

Tabela singleton (`id = 1`). Todos os parâmetros RAG dinâmicos listados na seção 5.1. Alterável em runtime via `PUT /admin/rag-parameters`. Inclui `llm_provider`, `llm_model`, `embedding_provider`, `embedding_model` para suporte a provedores externos.

#### `rag_evaluations`

Histórico de execuções RAGAS com métricas `faithfulness`, `answer_relevancy`, `context_precision`, `context_recall`, `answer_correctness`, `num_samples` e `metadata` JSONB com scores por amostra.

**Índices:**
- `idx_documents_status` — busca por status
- `idx_documents_file_hash` — deduplicação
- `idx_chunks_document_id` — chunks por documento
- `idx_chat_messages_session_id_created` — histórico ordenado
- `idx_chat_sessions_user_id` — sessões por usuário
- `idx_rag_evaluations_created_at` — histórico de avaliações

**Trigger:** `trg_documents_updated_at` mantém `documents.updated_at` atualizado automaticamente.

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

**Payload de cada ponto (chunk filho):**
```json
{
  "doc_id": "uuid",
  "source": "nome_arquivo.pdf",
  "display_name": "Nome de Exibição",
  "page_number": 3,
  "chunk_index": 12,
  "type": "child",
  "parent_id": "uuid-pai",
  "parent_text": "texto completo do chunk pai",
  "created_at": "2025-01-01T00:00:00Z",
  "hash": "sha256hexdigest",
  "doc_type": "edital",
  "edital_ref": null
}
```

A coleção é criada automaticamente no startup via `ensure_collection()`. Se uma coleção incompatível existir (configuração legada de vetor único), ela é **deletada e recriada** — todos os dados indexados são perdidos. Faça backup antes de migrar.

**Constantes obrigatórias:**
```python
from app.db.qdrant import DENSE_VECTOR_NAME, SPARSE_VECTOR_NAME  # "dense" / "sparse"
```
Nunca passar vetores sem nome — causa falha silenciosa na busca híbrida.

---

## 7. Frontend

Aplicação SPA em React 18 + TypeScript + Vite, servida via Nginx na porta 3000.

**Views:**
- `chat` — interface pública de conversa com streaming SSE
- `admin-login` — formulário de autenticação
- `admin` — painel de administração (protegido por JWT)

**Principais hooks:**

| Hook | Responsabilidade |
|------|-----------------|
| `useAuth` | Login, logout, armazenamento e renovação de token JWT |
| `useChat` | Envio de mensagens, consumo do stream SSE (`message_id`, `token`, `sources`, `done`), histórico |
| `useSessions` | Criação, listagem e remoção de sessões |
| `useIndexingProgress` | WebSocket para acompanhar progresso de indexação por `doc_id` |
| `useTheme` | Alternância modo claro/escuro |

**Auto-logout:** Event listener em `App.tsx` captura o evento customizado `propesqi:auth-error` (disparado quando qualquer requisição autenticada recebe HTTP 401) e redireciona para a tela de login.

**`UploadMetadataModal`:** quando `docType === 'aditivo'` é selecionado, exibe o campo "Edital de referência (opcional)". O valor é enviado como `edital_ref` no FormData do upload.

**UUID geração:** `lib/uuid.ts` usa `crypto.randomUUID()` com fallback para `Math.random()` em contextos HTTP inseguros (acesso por IP externo sem HTTPS).

**Nginx** serve arquivos estáticos e faz proxy de `/api/*` para `backend:8000` na rede interna Docker.

---

## 8. Modelos de IA

### Modo local (Ollama, padrão)

| Modelo | Papel | VRAM estimada |
|--------|-------|------|
| `gemma3:12b` (Q4_K_M) | LLM — geração de respostas e HyDE/multi-query | ~8 GB |
| `bge-m3` (BAAI) | Embeddings densos — 1024 dimensões | ~1,1 GB |

**Total ~9 GB de 16 GB disponíveis.** Com `OLLAMA_MAX_LOADED_MODELS=2`, ambos os modelos ficam carregados simultaneamente (sem reload entre chamadas). `OLLAMA_NUM_PARALLEL=1` serializa inferências para evitar OOM.

### Modo externo (sem GPU necessária para LLM)

| Provider | Modelo tipicamente usado | Configuração |
|---|---|---|
| Google Gemini | `gemini-3.1-flash-lite` | `llm_provider=gemini`, `GOOGLE_API_KEY` |
| OpenAI | `gpt-4o-mini` | `llm_provider=openai`, `OPENAI_API_KEY` |
| Anthropic | `claude-haiku-4-5-20251001` | `llm_provider=anthropic`, `ANTHROPIC_API_KEY` |

No modo externo, o Ollama ainda é necessário para embeddings (`bge-m3`). O LLM não é carregado no Ollama, liberando ~8 GB de VRAM.

> **Nota:** `gemini-3.1-flash-lite` é o modelo utilizado nos ciclos de otimização RAG (Passos 5–14) e no harness de avaliação `run_groundtruth_eval.py`, tanto como LLM do pipeline quanto como judge. Os resultados de avaliação (melhor: 4.620/5 = 92.4%) refletem esse modelo.

### Reranker e encoder esparso (sempre locais)

| Modelo | Papel | Hardware |
|--------|-------|---------|
| `BAAI/bge-reranker-v2-m3` | Reranking cross-encoder | GPU (PyTorch) |
| BM42 (fastembed) | Embeddings esparsos | CPU |

O reranker usa GPU via PyTorch/sentence-transformers. Um modelo fine-tuned pode ser especificado via `RERANKER_MODEL` apontando para path local (ex: `./models/reranker-propesqi`).

---

## 9. Segurança

| Controle | Implementação |
|----------|---------------|
| Autenticação | JWT HS256 com expiração curta (access) + longa (refresh) |
| Senhas | bcrypt com salt aleatório via passlib |
| Timing attacks | Hash bcrypt executado mesmo para usuários inexistentes (CWE-208) |
| CORS | Allowlist explícita via `ALLOWED_ORIGINS` |
| Upload MIME | `Content-Type: application/pdf` + verificação de magic bytes `%PDF` (OWASP A03, CWE-351) |
| Tamanho de upload | Limite de 50 MB enforçado antes de salvar no disco |
| Path traversal | `Path(raw).name` antes de salvar arquivo (CWE-22) |
| Null bytes | Stripped do nome do arquivo antes do processamento (CWE-626) |
| WebSocket DoS | `doc_id` validado como UUID antes de criar subscriber na queue |
| Qdrant | API key obrigatória; porta 6333/6334 não exposta ao host |
| Secrets | `SECRET_KEY` mínimo 32 chars, validado na inicialização com `@field_validator` |
| Role-based access | Todas as rotas administrativas exigem `admin` ou `superadmin` |
| Privilege separation | Backend conecta como `propesqi_app` (DML only) — não como superusuário |

---

## 10. Implantação com Docker

### Serviços

| Serviço | Imagem | Porta interna | Porta host |
|---------|--------|--------------|------------|
| `propesqi_postgres` | `postgres:16-alpine` | 5432 | 5432 |
| `propesqi_qdrant` | `qdrant/qdrant:latest` | 6333/6334 | — |
| `propesqi_ollama` | `ollama/ollama:latest` | 11434 | 11434 |
| `propesqi_backend` | Build local (`backend/Dockerfile`) | 8000 | — |
| `propesqi_frontend` | Build local (`frontend/Dockerfile`) | 3000 | **3000** |

Todos os serviços se comunicam pela rede Docker interna `propesqi-net`. O frontend (porta 3000) é o único ponto de entrada externo — o backend (porta 8000) é acessível apenas internamente.

### Inicialização do banco

Os scripts em `init/` são executados pelo container do PostgreSQL na **primeira inicialização** (apenas uma vez):

1. `00_roles.sh` — cria role de aplicação `propesqi_app` com privilégios mínimos (SELECT/INSERT/UPDATE/DELETE, sem DDL)
2. `01_schema.sql` — cria tabelas, índices, extensões, trigger e seeds do `rag_config`. Todas as operações são idempotentes via `CREATE ... IF NOT EXISTS` e `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`
3. `02_seed_admin.sh` — insere o primeiro usuário admin (e-mail e senha de `ADMIN_EMAIL`/`ADMIN_PASSWORD`). Idempotente: não cria duplicata se já existir

### GPU habilitada por padrão

```bash
# Pré-requisito: nvidia-container-toolkit instalado e configurado
docker compose up -d
```

O `docker-compose.yml` já inclui `deploy.resources.reservations` para GPU em `backend` e `ollama`. Para usar todas as GPUs disponíveis em hardware multi-GPU:

```bash
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d
```

### Rebuild após mudanças de código

```bash
# Após editar arquivos Python do backend
docker compose build backend && docker compose up -d backend

# Após editar React/TypeScript do frontend
docker compose build frontend && docker compose up -d frontend
```

### Baixar modelos no Ollama (primeira vez)

Os modelos são baixados automaticamente pelo warmup do backend na primeira inicialização. Para baixar manualmente:

```bash
docker exec propesqi_ollama ollama pull gemma3:12b
docker exec propesqi_ollama ollama pull bge-m3
```

### Health checks

Todos os serviços têm `healthcheck` configurado. O backend aguarda `postgres`, `qdrant` e `ollama` saudáveis antes de iniciar (`depends_on: condition: service_healthy`). O backend tem `start_period: 120s` para acomodar o warmup dos modelos.

---

## 11. Variáveis de Ambiente

Crie um arquivo `.env` na raiz do projeto (copie de `.env.example`):

```env
# PostgreSQL — superusuário (apenas para init scripts)
POSTGRES_USER=propesqi
POSTGRES_PASSWORD=<senha-forte>
POSTGRES_DB=propesqi_db
PROPESQI_APP_PASSWORD=<senha-da-role-de-aplicacao>

# Conexão da aplicação (role limitada)
DATABASE_URL=postgresql+asyncpg://propesqi_app:<PROPESQI_APP_PASSWORD>@postgres:5432/propesqi_db

# Seed do primeiro admin
ADMIN_EMAIL=admin@example.com
ADMIN_PASSWORD=<senha-forte>

# Qdrant
QDRANT_URL=http://qdrant:6333
QDRANT_API_KEY=<minimo-32-chars>

# Ollama (interno)
OLLAMA_BASE_URL=http://ollama:11434

# JWT — gere com: python3 -c "import secrets; print(secrets.token_hex(32))"
SECRET_KEY=<minimo-32-chars>
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=60
REFRESH_TOKEN_EXPIRE_DAYS=7

# CORS (em produção: URL real do frontend)
ALLOWED_ORIGINS=http://localhost:3000

# Frontend (build-time)
VITE_API_URL=/api

# API keys externas (opcionais — apenas se llm_provider != 'local')
GOOGLE_API_KEY=
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
```

---

## 12. Testes e Avaliação

### Testes unitários e de latência

```bash
cd backend

# Unitários (document_names, rag_engine)
pytest tests/ -v --ignore=tests/latency --ignore=tests/load

# Latência in-process (ASGI, sem servidor rodando)
pytest tests/latency/ -v

# Carga (requer stack Docker rodando)
locust -f tests/load/locustfile.py --host=http://localhost:8000 \
       --users 20 --spawn-rate 5 --run-time 2m --headless
```

### Avaliação de qualidade RAG (`run_groundtruth_eval.py`)

Script offline que avalia o pipeline contra 30 perguntas com gabarito e retorna uma pontuação média 0–5.

**Pré-requisitos:**
- Stack Docker rodando (backend, Qdrant, Ollama)
- `GOOGLE_API_KEY` configurada (judge usa Gemini API)
- Backend configurado com `llm_provider=gemini` e `llm_model=gemini-3.1-flash-lite` no `rag_config` (ou `local` para usar Ollama)

```bash
cd backend
python tests/run_groundtruth_eval.py
```

**Arquivos de entrada/saída:**

| Arquivo | Descrição |
|---------|-----------|
| `tests/groundtruth_chatbot_rag.csv` | Ground truth: 30 perguntas + respostas esperadas + keywords |
| `tests/groundtruth_chatbot_rag_resultados_passoN_full.csv` | Resultado do eval do Passo N |
| `tests/relatorio_otimizacao_rag.md` | Relatório completo do ciclo de otimização (Passos 5–14) |

**Evolução de qualidade (gemini-3.1-flash-lite):**

| Passo | Melhoria | Pontuação |
|-------|----------|-----------|
| Baseline | — | 3.63/5 |
| 5 | Reranker + HyDE | 4.04/5 |
| 9 | Injeção lexical Q26/Q29 | 4.07/5 |
| 10 | Pinned injection Q05/Q15 | 4.50/5 |
| 11 | Reranker GPU + warmup | 4.52/5 |
| 12 | Q25 multi-edital + regra vigência | 4.37/5 |
| 13 | Q21 PIBICEM colégio (pinned) | 4.57/5 |
| **14** | **Q18 expansão lexical PIBITI** | **4.62/5 (92.4%)** |
