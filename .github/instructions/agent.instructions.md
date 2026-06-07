---
description: Instruções gerais do projeto PROPESQI RAG Chatbot para todas as interações com o agente de IA.
applyTo: "**"
---

# PROPESQI RAG Chatbot — Instruções para o Agente de IA

## 1. Contexto do Projeto

Sistema de perguntas e respostas sobre documentos internos da **Pró-Reitoria de Pesquisa e Inovação (PROPESQI)** da **Universidade Federal do Piauí (UFPI)**. Opera 100% on-premise com LLM local em GPU **NVIDIA RTX 5060 Ti (16 GB VRAM)**.

- **Usuários finais:** servidores, alunos e pesquisadores da UFPI
- **Idioma padrão de toda a interface, respostas e código:** Português (Brasil)
- **Domínio:** documentos institucionais (editais, resoluções, regulamentos, manuais)

---

## 2. Stack Tecnológica

### Backend
| Componente | Tecnologia |
|---|---|
| Framework | FastAPI (Python 3.11+) |
| ORM | SQLAlchemy 2 async + asyncpg |
| Banco relacional | PostgreSQL 16 |
| Vector store | Qdrant (hybrid search BM42 + Dense) |
| LLM principal | `gemma3:12b` via Ollama |
| Embeddings | `bge-m3` (BAAI, 1024 dims) via Ollama |
| Reranker | `BAAI/bge-reranker-v2-m3` via sentence-transformers (CPU) |
| Encoder esparso | BM42 via fastembed |
| OCR | Tesseract 5 + OpenCV + pytesseract |
| Tokenizer | tiktoken `cl100k_base` |
| Autenticação | JWT HS256 + bcrypt (python-jose + passlib) |
| Avaliação RAG | RAGAS |
| Containerização | Docker Compose v2 |

### Frontend
| Componente | Tecnologia |
|---|---|
| Framework | React 18 + TypeScript + Vite |
| Estilização | Tailwind CSS |
| Servidor estático | Nginx (proxy `/api/*` → backend) |

---

## 3. Estrutura de Diretórios

```
chatbot/
├── docker-compose.yml
├── DOCUMENTATION.md        ← documentação técnica completa
├── PLANEJAMENTO.md         ← decisões de arquitetura e justificativas
├── init/
│   ├── 00_roles.sh         ← role limitada no PostgreSQL
│   └── 01_schema.sql       ← DDL (idempotente)
├── backend/
│   └── app/
│       ├── main.py         ← ponto de entrada FastAPI + lifespan
│       ├── api/routes/     ← auth, chat, documents, admin, evaluation, ws
│       ├── core/
│       │   ├── config.py        ← Settings (pydantic-settings, singleton @lru_cache)
│       │   ├── security.py      ← JWT, bcrypt, dependências de autorização
│       │   ├── rag_engine.py    ← pipeline RAG completo (gerador assíncrono rag_stream)
│       │   ├── evaluator.py     ← avaliação RAGAS
│       │   ├── progress.py      ← pub/sub in-process para WebSocket
│       │   └── document_names.py← normalização de nomes de exibição
│       ├── db/
│       │   ├── postgres.py      ← engine AsyncSA + fábrica de sessão
│       │   ├── qdrant.py        ← cliente Qdrant singleton + ensure_collection
│       │   ├── search.py        ← hybrid_search() + expand_to_parents()
│       │   ├── reranker.py      ← rerank() via sentence-transformers
│       │   └── rag_config.py    ← parâmetros RAG dinâmicos (lidos do PostgreSQL)
│       ├── ingestion/
│       │   ├── processor.py     ← orquestrador (BackgroundTask pós-upload)
│       │   ├── chunker.py       ← parent-child chunking com tiktoken
│       │   ├── sparse.py        ← encoder esparso BM42
│       │   └── extractors/
│       │       ├── pdf.py       ← extração nativa (pdfplumber/pypdf)
│       │       └── ocr.py       ← OCR com OpenCV + Tesseract
│       ├── models/              ← SQLAlchemy ORM models
│       └── schemas/             ← Pydantic request/response schemas
└── frontend/
    └── src/
        ├── App.tsx              ← roteamento de views (chat / admin)
        ├── components/
        │   ├── chat/            ← ChatWindow, MessageBubble, ChatInput
        │   ├── admin/           ← AdminPanel, DocumentTable, UploadZone, …
        │   └── layout/          ← Sidebar
        ├── hooks/               ← useAuth, useChat, useSessions, useIndexingProgress, useTheme
        └── lib/api.ts           ← cliente HTTP centralizado
```

---

## 4. Pipeline RAG — Fluxo Completo

O pipeline é implementado em `backend/app/core/rag_engine.py` como gerador assíncrono `rag_stream()`.

```
Pergunta do usuário
  1. Normalização de whitespace
  2. Guards especiais: saudações, identidade, vazio → resposta direta sem RAG
  3. HyDE — gera resposta hipotética via Ollama (temperature 0.3)
  4. Multi-query — MULTIQUERY_COUNT reformulações (default 2) via Ollama
  5. Busca híbrida no Qdrant para cada query (dense bge-m3 + sparse BM42, fusão RRF)
  6. Reranking — bge-reranker-v2-m3 (top_k=5, score_threshold=0.5)
  7. Fallback guard — se nenhum chunk sobreviver: retorna mensagem padrão
  8. expand_to_parents() — expande chunks filho para janela pai (512 tokens)
  9. Compressão contextual (se CONTEXTUAL_COMPRESSION_ENABLED=true)
  10. Montagem do prompt com histórico (últimas 10 mensagens do PostgreSQL)
  11. Streaming via Ollama /api/chat (gemma3:12b, temperature=0.1, max_tokens=1024)
  12. Emite eventos SSE: token → sources → done
  13. Persistência no PostgreSQL (mensagem + resposta + sources)
```

---

## 5. Modelos de IA

| Modelo | Papel | VRAM |
|---|---|---|
| `gemma3:12b` | LLM principal — geração de respostas | ~8 GB (Q4_K_M) |
| `bge-m3` (BAAI) | Embeddings densos (1024 dims) | ~1,1 GB |
| `bge-reranker-v2-m3` | Reranking cross-encoder | CPU |
| BM42 (fastembed) | Embeddings esparsos | CPU |

**Estratégia de VRAM (16 GB):**
- `OLLAMA_MAX_LOADED_MODELS=2` — gemma3 + bge-m3 carregados simultaneamente (~9 GB)
- `OLLAMA_NUM_PARALLEL=1` — serializa inferências para evitar thrashing de GPU

---

## 6. Banco de Dados

### PostgreSQL — Tabelas principais
| Tabela | Descrição |
|---|---|
| `documents` | Metadados de cada documento (status, hash SHA-256, tipo, total_chunks) |
| `chunks` | Metadados espelho dos pontos Qdrant (qdrant_id, page_number, text_preview) |
| `chat_sessions` | Sessões de conversa (anônimas ou autenticadas) |
| `chat_messages` | Mensagens com role, content, sources (JSONB), feedback |
| `users` | Usuários administrativos com role (admin / superadmin) |
| `rag_config` | Tabela singleton com parâmetros dinâmicos do pipeline RAG |
| `rag_evaluations` | Histórico de runs RAGAS com métricas agregadas |

### Qdrant — Coleção `propesqi_docs`
- **Vetores:** `dense` (1024 dims, cosine) + `sparse` (BM42, IDF modifier)
- **Payload por ponto:** `doc_id`, `source`, `display_name`, `page_number`, `chunk_index`, `parent_id`, `parent_text`, `text`, `text_preview`, `created_at`

---

## 7. API REST

### Endpoints principais
| Grupo | Rota | Auth |
|---|---|---|
| Autenticação | `POST /auth/login` | Pública |
| Chat | `POST /chat/sessions`, `POST /chat/stream`, `GET /chat/sessions/{id}/messages` | Pública/Opcional |
| Documentos | `POST /documents/upload`, `GET /documents/`, `DELETE /documents/{id}`, `POST /documents/reindex` | Admin |
| Admin | `GET /admin/rag-parameters`, `PUT /admin/rag-parameters` | Admin |
| Avaliação | `POST /evaluation/run`, `GET /evaluation/results` | Admin |
| WebSocket | `GET /ws/documents/{doc_id}/progress?token=<jwt>` | Admin |
| Health | `GET /health` | Pública |

### Eventos SSE do `/chat/stream`
| Evento | Dado |
|---|---|
| `token` | Fragmento de texto gerado pelo LLM |
| `sources` | Array JSON de SourceCitation |
| `done` | `"[DONE]"` |
| `error` | Mensagem de erro interno |

---

## 8. Segurança — Regras Obrigatórias

Ao gerar ou revisar código, sempre verificar:

- **Upload de arquivos:** validar `Content-Type`, magic bytes (`%PDF`), tamanho máximo (50 MB), sanitizar nome com `Path(raw).name` (CWE-22), remover null bytes (CWE-626)
- **JWT:** não usar algoritmo `none`; sempre validar `exp` e `role`
- **Senhas:** nunca armazenar em texto plano; sempre usar bcrypt
- **Timing attacks:** executar hash bcrypt mesmo quando usuário não existe (CWE-208)
- **CORS:** usar apenas origins da allowlist `ALLOWED_ORIGINS`
- **Secrets:** `SECRET_KEY` mínimo 32 chars; nunca commitar `.env`
- **WebSocket:** validar `doc_id` como UUID antes de criar subscriber (previne DoS)
- **SQL:** usar parâmetros ORM/SQLAlchemy; nunca concatenar strings em queries
- **Roles:** rotas administrativas sempre exigem `require_admin` dependency

---

## 9. Convenções de Código

### Python (Backend)
- Python 3.11+; usar `async/await` em todos os handlers FastAPI e operações de I/O
- Type hints obrigatórios em funções públicas
- Schemas Pydantic para todos os request/response bodies
- `get_settings()` (singleton `@lru_cache`) para acessar configurações — nunca ler `os.environ` diretamente
- Sessões de banco via dependency injection `get_db()` — nunca criar sessões manualmente dentro de handlers
- Erros de negócio: usar `HTTPException` com status codes semânticos
- Logs: usar `logger = logging.getLogger(__name__)` — nunca `print()`

### TypeScript (Frontend)
- React 18 funcional com hooks; sem componentes de classe
- Estado de autenticação exclusivamente via `useAuth`
- Todas as chamadas HTTP via `lib/api.ts` — nunca usar `fetch`/`axios` diretamente nos componentes
- Streaming SSE via `useChat` hook
- Erros 401 disparam evento customizado `propesqi:auth-error` (tratado em `App.tsx`)
- Tailwind para estilos — sem CSS inline exceto quando absolutamente necessário

### Docker
- Reconstruir apenas o serviço alterado: `docker compose up -d --build <serviço>`
- Serviços disponíveis: `postgres`, `qdrant`, `ollama`, `backend`, `frontend`
- Rede interna: `propesqi-net`
- Frontend exposto na porta `3000` do host; backend em `8000`

---

## 10. Parâmetros RAG Configuráveis

Todos os parâmetros abaixo são ajustáveis via `PUT /admin/rag-parameters` (sem reiniciar):

| Parâmetro | Padrão | Descrição |
|---|---|---|
| `parent_chunk_tokens` | 512 | Tamanho do chunk pai em tokens |
| `child_chunk_tokens` | 128 | Tamanho do chunk filho em tokens |
| `search_top_k` | 20 | Candidatos retornados pelo Qdrant |
| `search_score_threshold` | 0.0 | Score mínimo na busca vetorial |
| `reranker_top_k` | 5 | Chunks finais após reranking |
| `reranker_score_threshold` | 0.5 | Score mínimo pós-reranking |

Variáveis de ambiente (requerem restart):

| Variável | Padrão |
|---|---|
| `HYDE_TEMPERATURE` | 0.3 |
| `MULTIQUERY_COUNT` | 2 |
| `MULTIQUERY_TEMPERATURE` | 0.3 |
| `CONTEXTUAL_COMPRESSION_ENABLED` | true |
| `CONTEXTUAL_COMPRESSION_TEMPERATURE` | 0.1 |

---

## 11. Padrões de Resposta do LLM

O system prompt do assistente obriga:
1. Responder **exclusivamente** com base nos documentos fornecidos no contexto
2. Quando a informação não estiver disponível: *"Não possuo informações sobre este assunto em minha base de documentos. Para esclarecimentos adicionais, entre em contato diretamente com a PROPESQI."*
3. Nunca inventar datas, normas, nomes ou valores
4. Manter tom institucional, respeitoso e acessível ao público universitário
5. Responder sempre em **português formal**

---

## 12. Comandos Úteis

```bash
# Subir todos os serviços (CPU)
docker compose up -d

# Subir todos os serviços (GPU NVIDIA)
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d

# Reconstruir apenas o frontend
docker compose up -d --build frontend

# Reconstruir apenas o backend
docker compose up -d --build backend

# Baixar modelos Ollama
docker exec propesqi_ollama ollama pull gemma3:12b
docker exec propesqi_ollama ollama pull bge-m3

# Executar testes unitários
cd backend && pytest tests/ -v --ignore=tests/latency --ignore=tests/load

# Gerar SECRET_KEY
python3 -c "import secrets; print(secrets.token_hex(32))"

# Verificar logs de um serviço
docker compose logs -f backend
docker compose logs -f frontend
```

---

## 13. O que NÃO Fazer

- Não expor `SECRET_KEY`, senhas ou chaves de API em código ou logs
- Não usar `print()` no backend — usar `logging`
- Não criar sessões SQLAlchemy fora do padrão de dependency injection
- Não adicionar dependências sem atualizar `requirements.txt` (backend) ou `package.json` (frontend)
- Não modificar o esquema do banco sem atualizar `init/01_schema.sql`
- Não usar `docker-compose.gpu.yml` em máquinas sem nvidia-container-toolkit instalado
- Não chamar `fetch`/`axios` diretamente nos componentes React — sempre usar `lib/api.ts`
- Não expor a porta do Qdrant (6333) externamente em produção
