# Planejamento — RAG Chatbot PROPESQI / UFPI

> **Objetivo:** Sistema de perguntas e respostas sobre documentos internos da
> Pró-Reitoria de Pesquisa e Inovação (PROPESQI) da UFPI, rodando inteiramente
> on-premise, com LLM local na GPU NVIDIA RTX 5060 Ti 16 GB VRAM.

---

## 1. Visão Geral da Arquitetura

```
┌─────────────────────────────────────────────────────────────────┐
│                        FRONTEND (React + Vite)                  │
│   ┌──────────────────────┐   ┌──────────────────────────────┐   │
│   │  Visão Usuário       │   │  Visão Administrador         │   │
│   │  • Chat estilo GPT   │   │  • Upload de documentos      │   │
│   │  • Histórico         │   │  • Gestão da base (CRUD)     │   │
│   │  • Modo claro/escuro │   │  • Reindexação parcial/total │   │
│   └──────────┬───────────┘   └──────────────┬───────────────┘   │
└──────────────┼──────────────────────────────┼───────────────────┘
               │ HTTP / REST + WebSocket SSE  │
┌──────────────▼──────────────────────────────▼───────────────────┐
│                     BACKEND (FastAPI + Python)                   │
│                                                                  │
│  ┌─────────────────┐  ┌──────────────────┐  ┌───────────────┐   │
│  │  Auth Service   │  │  Chat Service    │  │  Admin Service│   │
│  │  (JWT + roles)  │  │  (RAG Pipeline)  │  │  (Ingestão)   │   │
│  └─────────────────┘  └────────┬─────────┘  └──────┬────────┘   │
│                                │                    │            │
│  ┌─────────────────────────────▼────────────────────▼─────────┐ │
│  │                    RAG Core Engine                          │ │
│  │                                                             │ │
│  │  Query Expansion → Hybrid Retrieval → Reranking → LLM      │ │
│  └──────┬───────────────────────┬────────────────────┬────────┘ │
│         │                       │                    │           │
└─────────┼───────────────────────┼────────────────────┼──────────┘
          │                       │                    │
┌─────────▼──────┐  ┌─────────────▼───────┐  ┌────────▼──────────┐
│  Qdrant        │  │  Ollama             │  │  PostgreSQL        │
│  (Vector DB)   │  │  LLM + Embeddings   │  │  (metadados,       │
│  Hybrid Search │  │  GPU RTX 5060 Ti    │  │   histórico,       │
│  BM25 + Dense  │  │  16 GB VRAM         │  │   usuários)        │
└────────────────┘  └─────────────────────┘  └───────────────────┘
          │
┌─────────▼──────────────────────────────────────────────────────┐
│                  Document Processor Pipeline                    │
│  PDF nativo → PyPDF / pdfplumber                               │
│  PDF digitalizado → Tesseract OCR + OpenCV (pré-processamento) │
│  DOCX / ODT → python-docx / unoconv                            │
│  Chunking → Sentence-Window + Parent-Child Splitter            │
└────────────────────────────────────────────────────────────────┘
```

---

## 2. Stack Tecnológica

| Camada | Tecnologia | Justificativa |
|---|---|---|
| Frontend | React 18 + Vite + TypeScript | Ecossistema maduro, SSE nativo |
| Estilização | Tailwind CSS + shadcn/ui | Componentes acessíveis, modo claro/escuro built-in |
| Backend | FastAPI (Python 3.11+) | Async nativo, WebSocket/SSE, tipagem forte |
| ORM | SQLAlchemy 2 + Alembic | Migrations controladas |
| Banco relacional | PostgreSQL 16 | Metadados, sessões, histórico de conversas |
| Vector Store | Qdrant (Docker) | Hybrid search BM25+Dense, payload filters, snapshots |
| Serving LLM local | Ollama | Gestão de modelos, CUDA nativo, API OpenAI-compatível |
| Orquestração RAG | LlamaIndex 0.10+ | Abstrações de alto nível para RAG avançado |
| OCR | Tesseract 5 + OpenCV + pytesseract | Reconhecimento robusto em PT-BR |
| Containerização | Docker Compose | Isolamento, reprodutibilidade, GPU passthrough |
| Autenticação | JWT (python-jose) + bcrypt | Stateless, seguro |

---

## 3. Modelos de IA — Seleção para RTX 5060 Ti 16 GB VRAM

### 3.1 LLM Principal

| Modelo | Quantização | VRAM estimada | Qualidade PT-BR | Recomendação |
|---|---|---|---|---|
| **Gemma 3 12B** | Q8_0 | ~13 GB | Excelente | **Principal** |
| Qwen 2.5 14B | Q4_K_M | ~8,5 GB | Excelente | Alternativa rápida |
| Llama 3.1 8B | Q8_0 | ~9 GB | Muito boa | Fallback leve |
| Mistral Small 3.1 22B | Q3_K_M | ~9 GB | Boa | Alternativa |

> **Escolha principal: `gemma3:12b-instruct-q8_0`** via Ollama
> - Melhor balanço qualidade/VRAM na faixa de 12–16 GB
> - Excelente compreensão e geração em Português formal
> - Suporte a contexto longo (128k tokens) — essencial para documentos extensos
> - Deixa ~3 GB de margem para KV-cache e operações concorrentes

### 3.2 Modelo de Embeddings

| Modelo | Dimensões | VRAM | Multilíngue | Recomendação |
|---|---|---|---|---|
| **BAAI/bge-m3** | 1024 | ~0,6 GB (CPU/GPU) | Sim (100+ idiomas) | **Principal** |
| nomic-embed-text v1.5 | 768 | ~0,3 GB | Não (EN foco) | Alternativa |
| mxbai-embed-large | 1024 | ~0,6 GB | Parcial | Alternativa |

> **Escolha: `bge-m3`** via Ollama
> - Suporte nativo a Português
> - Suporta Dense + Sparse embeddings (crucial para hybrid search)
> - Dimensão 1024 oferece alta fidelidade semântica

### 3.3 Modelo de Reranking

- **`BAAI/bge-reranker-v2-m3`** (cross-encoder) — rodando via `sentence-transformers`
- Executa na CPU ou GPU com baixo consumo (~0,3 GB VRAM)

---

## 4. Pipeline RAG — Fluxo Detalhado

### 4.1 Ingestão de Documentos

```
Documento recebido
       │
       ▼
┌─────────────────────────────────────────┐
│ 1. Detecção de tipo                     │
│    • PDF nativo vs. digitalizado        │
│    • DOCX, ODT, TXT                     │
└──────────────────┬──────────────────────┘
                   │
       ┌───────────▼────────────┐
       │ PDF digitalizado?       │
       └───┬───────────────┬────┘
           │ Sim            │ Não
           ▼                ▼
  ┌────────────────┐  ┌──────────────────┐
  │ OCR Pipeline   │  │ Extração direta  │
  │ • OpenCV       │  │ • pdfplumber     │
  │   (deskew,     │  │ • pypdf          │
  │    denoise,    │  │ • python-docx    │
  │    threshold)  │  └────────┬─────────┘
  │ • Tesseract 5  │           │
  │   (PT-BR)      │           │
  └────────┬───────┘           │
           └──────────┬────────┘
                      ▼
           ┌──────────────────────┐
           │ 2. Limpeza de texto  │
           │ • Remoção de ruído   │
           │ • Normalização UTF-8 │
           │ • Deduplicação       │
           └──────────┬───────────┘
                      ▼
           ┌──────────────────────────────────┐
           │ 3. Chunking (Hierárquico)         │
           │                                  │
           │  Parent Chunk (512 tokens)        │
           │  └─ Child Chunk  (128 tokens) ×N  │
           │     └─ Sentence Window (±2 sent.) │
           │                                  │
           │  Metadados por chunk:             │
           │  • doc_id, source, page, type     │
           │  • created_at, hash (SHA-256)     │
           └──────────┬───────────────────────┘
                      ▼
           ┌──────────────────────┐
           │ 4. Geração de        │
           │    Embeddings        │
           │    (bge-m3)          │
           │  • Dense vector      │
           │  • Sparse vector     │
           └──────────┬───────────┘
                      ▼
           ┌──────────────────────┐
           │ 5. Indexação Qdrant  │
           │    + Metadata SQL    │
           └──────────────────────┘
```

### 4.2 Query Pipeline — Resposta ao Usuário

```
Pergunta do usuário
        │
        ▼
┌─────────────────────────────────────────────────────────┐
│ 1. Query Preprocessing                                  │
│    • Detecção de idioma                                 │
│    • Normalização (acentuação, maiúsculas)              │
└──────────────────────┬──────────────────────────────────┘
                       │
        ┌──────────────▼──────────────┐
        │ 2. Query Expansion (HyDE)   │
        │    • LLM gera resposta      │
        │      hipotética             │
        │    • Expande semântica da   │
        │      busca sem custo        │
        └──────────────┬──────────────┘
                       │
        ┌──────────────▼──────────────┐
        │ 3. Multi-Query Retrieval    │
        │    • 3 variações da pergunta│
        │      geradas pelo LLM       │
        │    • Resultado: union set   │
        └──────────────┬──────────────┘
                       │
        ┌──────────────▼──────────────┐
        │ 4. Hybrid Search (Qdrant)   │
        │    • Dense search (bge-m3)  │
        │    • Sparse search (BM25)   │
        │    • RRF fusion (α=0.7)     │
        │    • Top-K = 20 candidatos  │
        └──────────────┬──────────────┘
                       │
        ┌──────────────▼──────────────┐
        │ 5. Reranking                │
        │    bge-reranker-v2-m3       │
        │    • Seleciona Top-5        │
        │    • Score threshold ≥ 0.5  │
        └──────────────┬──────────────┘
                       │
        ┌──────────────▼──────────────┐
        │ 6. Context Assembly         │
        │    • Parent-Child: expande  │
        │      chunks para janela     │
        │      maior (512 tokens)     │
        │    • Deduplicação de chunks │
        │    • Histórico da conversa  │
        │      (últimas 5 trocas)     │
        └──────────────┬──────────────┘
                       │
        ┌──────────────▼──────────────┐
        │ 7. Prompt Engineering       │
        │    (System Prompt PROPESQI) │
        │    • Instruções de tom      │
        │    • Regra de groundedness  │
        │    • Resposta apenas dos    │
        │      documentos fornecidos  │
        └──────────────┬──────────────┘
                       │
        ┌──────────────▼──────────────┐
        │ 8. LLM Generation           │
        │    gemma3:12b via Ollama    │
        │    • Streaming (SSE)        │
        │    • Temperature = 0.1      │
        │    • Max tokens = 1024      │
        └──────────────┬──────────────┘
                       │
        ┌──────────────▼──────────────┐
        │ 9. Post-processing          │
        │    • Citação das fontes     │
        │    • Verificação se há      │
        │      resposta nos docs      │
        │    • Salvamento no histórico│
        └─────────────────────────────┘
```

---

## 5. Técnicas de Otimização RAG

### 5.1 Otimização de Recuperação

| Técnica | Descrição | Impacto |
|---|---|---|
| **Hybrid Search (BM25 + Dense)** | Combina busca lexical e semântica via RRF | +15–20% recall |
| **HyDE** | Gera documento hipotético para enriquecer embedding da query | +10–15% precision |
| **Multi-Query** | 3 reformulações da pergunta, union dos resultados | Reduz miss por paráfrase |
| **Parent-Child Retrieval** | Indexa chunks pequenos, retorna contexto maior | Melhor coerência |
| **Sentence Window** | Janela de ±2 sentenças ao redor do match | Contexto local completo |

### 5.2 Otimização de Ranking

| Técnica | Descrição |
|---|---|
| **Cross-Encoder Reranker** | Avalia relevância query↔chunk em par, mais preciso que cosine |
| **Score Threshold** | Descarta chunks com score < 0.5 (evita alucinação por contexto fraco) |
| **MMR (Maximal Marginal Relevance)** | Diversifica resultados, evita chunks redundantes |

### 5.3 Otimização de Geração

| Técnica | Descrição |
|---|---|
| **Grounding Explícito** | System prompt proíbe inferências fora dos documentos |
| **Temperature baixa (0.1)** | Respostas determinísticas e factuais |
| **Streaming SSE** | Latência percebida menor (primeira palavra em ~0,5s) |
| **Contextual Compression** | LLM extrai apenas partes relevantes dos chunks antes de gerar |
| **Fallback educado** | Se score máximo < 0.3, responde que não possui informação |

### 5.4 System Prompt Base

```
Você é o assistente virtual da Pró-Reitoria de Pesquisa e Inovação (PROPESQI)
da Universidade Federal do Piauí (UFPI). Responda sempre em português formal
e de forma clara e objetiva.

REGRAS OBRIGATÓRIAS:
1. Responda EXCLUSIVAMENTE com base nos documentos fornecidos no contexto.
2. Se a informação não estiver nos documentos, responda:
   "Não possuo informações sobre este assunto em minha base de documentos.
    Para esclarecimentos adicionais, entre em contato diretamente com a PROPESQI."
3. Nunca invente datas, normas, nomes ou valores.
4. Ao final de cada resposta, cite as fontes utilizadas (nome do documento e página).
5. Mantenha tom institucional, respeitoso e acessível ao público universitário.

CONTEXTO DOS DOCUMENTOS:
{context}

HISTÓRICO DA CONVERSA:
{chat_history}
```

---

## 6. Processamento de Documentos e OCR

### 6.1 Pipeline OCR Detalhado

```python
# Fluxo: PDF digitalizado → texto limpo

1. pdf2image    → converte páginas em imagens (300 DPI)
2. OpenCV       → pré-processamento:
                  • cv2.fastNlMeansDenoisingColored()  # remoção de ruído
                  • cv2.threshold() (Otsu binarization) # binarização
                  • deskew (correção de inclinação)
                  • remoção de bordas/margens sujas
3. Tesseract 5  → OCR com:
                  • lang="por"  (modelo PT-BR)
                  • --oem 3     (LSTM engine)
                  • --psm 3     (auto page segmentation)
4. pós-OCR      → hifenização, espaços duplos, limpeza de artefatos
```

### 6.2 Tipos de Documentos Suportados

| Formato | Biblioteca | Notas |
|---|---|---|
| PDF nativo (texto) | pdfplumber + pypdf | Preserva estrutura, tabelas |
| PDF digitalizado | pdf2image + Tesseract | OCR automático detectado |
| DOCX / DOC | python-docx | Preserva formatação e seções |
| ODT | odfpy | Compatibilidade LibreOffice |
| TXT / MD | nativo | Passagem direta |

### 6.3 Detecção Automática PDF Digitalizado

- Heurística: se texto extraído por pdfplumber < 50 chars/página → assume digitalizado
- Fallback para OCR automático sem intervenção manual

---

## 7. Gestão da Base de Conhecimento (Admin)

### 7.1 Operações de Reindexação

```
Reindexação TOTAL
  • Apaga toda a coleção Qdrant
  • Reprocessa todos os documentos da fila
  • Atualiza metadados no PostgreSQL
  • Útil após mudança de modelo de embeddings

Reindexação PARCIAL (incremental)
  • Processa apenas documentos com status = "pending"
  • Usa SHA-256 hash para evitar reprocessamento de docs não alterados
  • Permite adicionar novos documentos sem reprocessar os existentes

Remoção de Documento
  • Deleta todos os chunks do Qdrant (filter por doc_id)
  • Remove metadados do PostgreSQL
  • Mantém log de auditoria
```

### 7.2 Estados dos Documentos

```
uploaded → processing → indexed → active
                ↓
             error → retry (max 3x)
```

---

## 8. Interfaces de Usuário

### 8.1 Visão Usuário — Chat

```
┌──────────────────────────────────────────────────────┐
│  [Logo PROPESQI]  Assistente PROPESQI    [☀/🌙]      │
├──────────────────────────────────────────────────────┤
│                                                      │
│  ┌──────────────────────────────────────────────┐   │
│  │  Bem-vindo! Como posso ajudá-lo(a)?          │   │
│  └──────────────────────────────────────────────┘   │
│                                                      │
│  ┌──────────────────────────────────────────────┐   │
│  │ [Usuário]: Como solicitar bolsa de iniciação │   │
│  │ científica?                                  │   │
│  └──────────────────────────────────────────────┘   │
│                                                      │
│  ┌──────────────────────────────────────────────┐   │
│  │ [Assistente]: Conforme o Edital nº XX/2024,  │   │
│  │ a solicitação de bolsa PIBIC deve ser feita  │   │
│  │ mediante...                                  │   │
│  │                                              │   │
│  │ 📄 Fonte: Edital_PIBIC_2024.pdf, pág. 3     │   │
│  └──────────────────────────────────────────────┘   │
│                                                      │
├──────────────────────────────────────────────────────┤
│  [Nova conversa]                                     │
│  ┌─────────────────────────────────────┐  [Enviar]  │
│  │ Digite sua pergunta...              │            │
│  └─────────────────────────────────────┘            │
└──────────────────────────────────────────────────────┘

Funcionalidades:
• Histórico de conversas na barra lateral (colapsável)
• Streaming em tempo real das respostas
• Citação de fontes clicável (abre doc na página citada)
• Botão "Copiar resposta"
• Toggle modo claro / escuro
• Feedback de resposta (👍 👎)
```

### 8.2 Visão Administrador

```
┌──────────────────────────────────────────────────────┐
│  [Logo] Admin PROPESQI              [Sair] [☀/🌙]    │
├────────────────┬─────────────────────────────────────┤
│ MENU           │  PAINEL PRINCIPAL                   │
│                │                                     │
│ 📊 Dashboard   │  ┌──────────┐ ┌──────────┐          │
│ 📄 Documentos  │  │ 12 docs  │ │ 3.847    │          │
│ 🔄 Indexação   │  │ ativos   │ │ chunks   │          │
│ 💬 Conversas   │  └──────────┘ └──────────┘          │
│ ⚙️  Config     │                                     │
│                │  DOCUMENTOS                         │
│                │  ┌────────────────────────────────┐ │
│                │  │ Nome          Status   Ações    │ │
│                │  │ Edital_PIBIC  ✅ ativo  [🗑️][↺] │ │
│                │  │ Resolucao_42  ✅ ativo  [🗑️][↺] │ │
│                │  │ Manual_PG     ⏳ proc.  [...]   │ │
│                │  └────────────────────────────────┘ │
│                │                                     │
│                │  [+ Adicionar Documento]            │
│                │                                     │
│                │  REINDEXAÇÃO                        │
│                │  [Parcial (novos)] [Total (reset)]  │
└────────────────┴─────────────────────────────────────┘

Funcionalidades:
• Upload múltiplo (drag-and-drop)
• Progresso de processamento em tempo real (WebSocket)
• Visualização de chunks indexados por documento
• Log de erros de OCR/processamento
• Estatísticas de uso (perguntas/dia, documentos mais consultados)
• Configuração de parâmetros RAG (threshold, top-k)
```

---

## 9. Modelo de Dados

### 9.1 PostgreSQL — Tabelas Principais

```sql
-- Documentos
documents (
  id UUID PRIMARY KEY,
  filename TEXT,
  original_name TEXT,
  file_hash SHA256,
  file_type TEXT,            -- pdf_native | pdf_scanned | docx | txt
  ocr_applied BOOLEAN,
  status TEXT,               -- uploaded | processing | indexed | active | error
  total_chunks INTEGER,
  created_at TIMESTAMP,
  updated_at TIMESTAMP
)

-- Chunks (metadados espelho do Qdrant)
chunks (
  id UUID PRIMARY KEY,
  document_id UUID REFERENCES documents,
  qdrant_id UUID,
  page_number INTEGER,
  chunk_index INTEGER,
  text_preview TEXT,         -- primeiros 200 chars
  created_at TIMESTAMP
)

-- Sessões de Chat
chat_sessions (
  id UUID PRIMARY KEY,
  user_id UUID,              -- NULL para usuário público (sem login)
  created_at TIMESTAMP,
  last_activity TIMESTAMP
)

-- Mensagens
chat_messages (
  id UUID PRIMARY KEY,
  session_id UUID REFERENCES chat_sessions,
  role TEXT,                 -- user | assistant
  content TEXT,
  sources JSONB,             -- [{doc_id, page, score}]
  created_at TIMESTAMP
)

-- Usuários Admin
users (
  id UUID PRIMARY KEY,
  email TEXT UNIQUE,
  password_hash TEXT,
  role TEXT,                 -- admin | superadmin
  created_at TIMESTAMP
)
```

---

## 10. Estrutura de Diretórios do Projeto

```
propesqi-chatbot/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   ├── routes/
│   │   │   │   ├── chat.py          # SSE streaming, histórico
│   │   │   │   ├── documents.py     # CRUD docs, upload
│   │   │   │   ├── indexing.py      # reindexação parcial/total
│   │   │   │   └── auth.py          # login, JWT
│   │   ├── core/
│   │   │   ├── rag_engine.py        # pipeline completo
│   │   │   ├── retriever.py         # hybrid search + reranker
│   │   │   ├── llm_client.py        # Ollama wrapper
│   │   │   └── embeddings.py        # bge-m3 wrapper
│   │   ├── ingestion/
│   │   │   ├── processor.py         # orquestrador de ingestão
│   │   │   ├── ocr.py               # Tesseract + OpenCV
│   │   │   ├── chunker.py           # parent-child splitter
│   │   │   └── extractors/          # pdf, docx, txt
│   │   ├── models/                  # SQLAlchemy models
│   │   ├── schemas/                 # Pydantic schemas
│   │   └── db/                      # conexões Qdrant + Postgres
│   ├── requirements.txt
│   └── Dockerfile
│
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── chat/                # ChatWindow, MessageBubble, Input
│   │   │   └── admin/               # DocumentTable, UploadZone, IndexPanel
│   │   ├── pages/
│   │   │   ├── Chat.tsx
│   │   │   └── Admin.tsx
│   │   ├── hooks/                   # useChat, useDocuments, useTheme
│   │   └── lib/                     # api client, formatters
│   ├── package.json
│   └── Dockerfile
│
├── docker-compose.yml
├── docker-compose.gpu.yml           # override com GPU passthrough
├── .env.example
└── PLANEJAMENTO.md
```

---

## 11. Docker Compose — Serviços

```yaml
services:
  postgres:
    image: postgres:16-alpine
    volumes:
      - postgres_data:/var/lib/postgresql/data

  qdrant:
    image: qdrant/qdrant:latest
    volumes:
      - qdrant_data:/qdrant/storage

  ollama:
    image: ollama/ollama:latest
    deploy:
      resources:
        reservations:
          devices:
            - capabilities: [gpu]       # RTX 5060 Ti
    volumes:
      - ollama_data:/root/.ollama

  backend:
    build: ./backend
    depends_on: [postgres, qdrant, ollama]
    environment:
      - OLLAMA_BASE_URL=http://ollama:11434
      - QDRANT_URL=http://qdrant:6333
      - DATABASE_URL=postgresql://...

  frontend:
    build: ./frontend
    ports:
      - "3000:3000"
    depends_on: [backend]
```

---

## 12. Roadmap de Implementação

### Fase 1 — Fundação (Semana 1–2)
- [ ] Configurar Docker Compose (Postgres, Qdrant, Ollama)
- [ ] Baixar e testar modelos no Ollama (`gemma3:12b`, `bge-m3`)
- [ ] Implementar pipeline de ingestão básico (PDF nativo)
- [ ] Implementar OCR pipeline (Tesseract + OpenCV)
- [ ] API de upload e indexação

### Fase 2 — RAG Core (Semana 3–4)
- [ ] Hybrid search no Qdrant (BM25 + Dense)
- [ ] Reranker (bge-reranker-v2-m3)
- [ ] Parent-Child chunking
- [ ] Chat endpoint com streaming SSE
- [ ] Manutenção de histórico de conversa

### Fase 3 — Frontend (Semana 5–6)
- [ ] Interface de chat (modo usuário) — estilo ChatGPT
- [ ] Modo claro / escuro com Tailwind
- [ ] Painel admin (upload, gestão, reindexação)
- [ ] Progresso de indexação em tempo real (WebSocket)

### Fase 4 — Otimização e QA (Semana 7–8)
- [ ] HyDE + Multi-Query Expansion
- [ ] Contextual Compression
- [ ] Testes de qualidade RAG (RAGAS framework)
- [ ] Ajuste fino dos parâmetros (chunk size, top-k, threshold)
- [ ] Testes de carga e latência

---

## 13. Estimativa de Latência

| Etapa | Tempo estimado |
|---|---|
| Embedding da query | ~50 ms |
| HyDE + Multi-query (LLM) | ~1–2 s |
| Hybrid search Qdrant | ~20–50 ms |
| Reranking (cross-encoder) | ~100–200 ms |
| Geração LLM (primeiros tokens) | ~500 ms |
| Geração completa (streaming) | ~3–8 s |
| **Total (percebido pelo usuário)** | **~1–2 s até primeiro token** |

---

## 14. Considerações de Segurança

- Autenticação admin via JWT com expiração curta (1h) + refresh token
- Upload restrito a tipos de arquivo permitidos (allowlist)
- Sanitização de filenames (path traversal prevention)
- Rate limiting na API de chat (evitar abuso)
- Isolamento de rede: Qdrant e Postgres não expostos externamente
- Logs de auditoria para todas as ações admin
- Variáveis sensíveis apenas em `.env` (nunca no repositório)
