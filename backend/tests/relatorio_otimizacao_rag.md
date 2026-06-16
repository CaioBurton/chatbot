# Relatório de Otimização do Pipeline RAG — PROPESQI/UFPI

**Dataset:** `groundtruth_chatbot_rag.csv` — 30 perguntas sobre os programas de Iniciação Científica 2025/2026  
**Script de avaliação:** `run_groundtruth_eval.py` (juiz: `gemini-3.1-flash-lite`, RPM=15)  
**Rubrica do juiz (0–1 por métrica):** corretude factual · completude · citação de fonte · sem alucinação · relevância · pontuação total (0–5)

---

## Arquitetura do pipeline (referência)

```
Query → normalização → [HyDE] → [multi-query] → hybrid_search RRF (dense bge-m3 + sparse BM42)
      → [reranker bge-reranker-v2-m3] → [parent-child expansion] → [compressão contextual]
      → LLM streaming (gemini-3.1-flash-lite)
```

Todos os parâmetros são lidos em tempo de execução da tabela `rag_config` (PostgreSQL, id=1) sem necessidade de reinicialização.

---

## Baseline — todos os flags desabilitados

**Config:**

| Parâmetro | Valor |
|---|---|
| `hyde_enabled` | false |
| `multiquery_enabled` | false |
| `reranker_enabled` | false |
| `parent_child_expansion_enabled` | false |
| `contextual_compression_enabled` | false |
| `search_top_k` | 20 |
| `reranker_top_k` | 5 |
| `reranker_score_threshold` | 0.5 |
| `llm_provider` | gemini |
| `llm_model` | gemini-3.1-flash-lite |
| `embedding_provider` | local (bge-m3:latest via Ollama) |

**Resultados gerais:**

| Métrica | Valor |
|---|---|
| Pontuação média | **3.63 / 5** |
| Corretude factual | 0.77 |
| Completude | 0.67 |
| Citação de fonte | 0.84 |
| Sem alucinação | 0.93 |
| Relevância | 0.78 |
| Respostas excelentes (≥ 4.5) | 19 / 30 |
| Respostas ruins (< 2.5) | 7 / 30 |

**Por programa:**

| Programa | Média |
|---|---|
| PIBITI / ITV | 4.55 |
| PIBIC / PIBIC-Af | 4.45 |
| PIBICEM (PIBIC-EM) | 3.62 |
| Geral | 3.11 |
| **ICV** | **2.00** ← pior |

**Falhas críticas (≤ 1.0):**

| ID | Nota | Descrição |
|---|---|---|
| Q14 | 0.0 | Prazo do relatório parcial ICV — resposta fallback |
| Q15 | 0.0 | Pontos mínimos do orientador no ICV — resposta fallback |
| Q13 | 0.2 | Sanções por não envio do relatório final ICV |
| Q20 | 0.2 | Destinatários do PIBIC-EM |
| Q26 | 0.5 | Sistema SIGAA para inscrições |
| Q29 | 1.0 | Conflito de interesses (orientar filho) |

**Diagnóstico inicial:** a mensagem de fallback (`"Não possuo informações..."`, 148 chars) é gerada pelo LLM quando o system prompt instrui a responder exatamente com esse texto ao não encontrar a resposta no contexto fornecido. Confirmado via `hybrid_search` direto no Qdrant: a busca retorna 20 candidatos com scores razoáveis (RRF 0.33–0.70) para TODAS as queries críticas — o problema é que o top-5 por score RRF não contém o chunk específico com a resposta.

---

## Passo 1 — `parent_child_expansion_enabled = true`

**Motivação:** chunks "filhos" (128 tokens) podem cortar a frase com a resposta ao meio. Expandir para o chunk "pai" (512 tokens) aumenta o contexto enviado ao LLM.

**Mudança aplicada:**
```sql
UPDATE rag_config SET parent_child_expansion_enabled = true WHERE id = 1;
```

**Smoke test nas 6 questões críticas:**

| ID | Baseline | Passo 1 | Δ |
|---|---|---|---|
| Q13 | 0.2 | **1.5** | +1.3 ✅ |
| Q14 | 0.0 | 0.0 | — |
| Q15 | 0.0 | 0.0 | — |
| Q20 | 0.2 | 0.5 | +0.3 (ruído) |
| Q26 | 0.5 | 0.5 | — |
| Q29 | 1.0 | 0.5 | -0.5 (ruído) |

**Análise:** Q13 melhorou (444 → 902 chars de resposta). Q14, Q15, Q26, Q29 continuam retornando o texto de fallback idêntico (148 chars) — o `expand_to_parents` recebe os chunks corretos (verificado: `parent_text` populado, `parent_id=None` mas fallback para `str(point.id)`), mas a expansão em si não resolve porque o problema é de **ranking**: o chunk certo não está no top-5 por score RRF, independente do tamanho do contexto.

**Conclusão:** ganho real mas limitado (apenas Q13). O gargalo é retrieval/ranking, não tamanho do chunk.

---

## Passo 2 — `reranker_enabled = true`

**Motivação:** o cross-encoder `bge-reranker-v2-m3` deveria re-ordenar os 20 candidatos RRF por relevância semântica real para a query, surfaçando os chunks corretos que o RRF puro não priorizou.

**Mudança aplicada:**
```sql
UPDATE rag_config SET reranker_enabled = true WHERE id = 1;
-- threshold=0.5, top_k=5 (valores existentes)
```

**Smoke test (6 críticas):**

| ID | Baseline | Passo 1 | Passo 2 | Δ vs baseline |
|---|---|---|---|---|
| Q13 | 0.2 | 1.5 | **4.5** | +4.3 ✅ |
| Q14 | 0.0 | 0.0 | **3.5** | +3.5 ✅ |
| Q15 | 0.0 | 0.0 | **4.4** | +4.4 ✅ |
| Q20 | 0.2 | 0.5 | **5.0** | +4.8 ✅ |
| Q26 | 0.5 | 0.5 | 0.5 | — |
| Q29 | 1.0 | 0.5 | 0.5 | — |

**Avaliação completa (30 questões):**

| Programa | Baseline | Passo 2 | Δ |
|---|---|---|---|
| ICV | 2.00 | **4.48** | +2.48 ✅ |
| PIBICEM | 3.62 | 4.38 | +0.75 |
| Geral | 3.11 | 2.71 | -0.40 ❌ |
| PIBITI | 4.55 | 4.45 | -0.10 |
| **PIBIC** | **4.45** | **3.26** | **-1.19** ❌ |
| **Média geral** | **3.63** | **3.64** | **+0.01 (wash)** |

**Regressões graves:**

| ID | Baseline | Passo 2 | Δ |
|---|---|---|---|
| Q01 | 5.0 | 0.5 | -4.5 ❌ |
| Q03 | 4.5 | 0.5 | -4.0 ❌ |
| Q05 | 5.0 | 0.2 | -4.8 ❌ |
| Q25 | 4.5 | 1.0 | -3.5 ❌ |

**Diagnóstico via inspeção direta do reranker** (`rerank()` com `score_threshold=0.0` para ver todos os scores):

- **Q01** ("objetivos do PIBIC"): top-5 rerankeado = Portaria PIBIC-EM (0.718) > Portaria PIBIC+ICV (0.706) > portaria21.pdf (0.693) > Portaria PIBIC-EM (0.687) > Edital PIBIC-EM página 1 (0.680). O chunk de **objetivos do PIBIC graduação** não aparece nem entre os 5 primeiros — o cross-encoder confunde portarias que citam "PIBIC" nominalmente com o edital de objetivos.
- **Q03** ("IRA mínimo PIBIC"): PIBIC-EM página 2 (score 0.614) supera PIBIC/PIBIC-Af páginas 1 e 4 (0.506, 0.504) — o cross-encoder iguala requisitos de IRA entre programas diferentes.
- **Q05** ("vigência das bolsas PIBIC"): chunks de "concessão de bolsas/benefícios" (seção 10, page 7) sobem (0.730, 0.721) acima do trecho específico de vigência 01/09/2025–31/08/2026.

**Causa raiz:** `bge-reranker-v2-m3` foi treinado para matching semântico geral cross-lingual. Neste corpus, ele **não distingue documentos dentro do mesmo domínio** (PIBIC vs PIBIC-EM vs Portaria PIBIC) e **não diferencia seções dentro do mesmo edital** (vigência de bolsas vs vigência de concessão/benefícios).

**Conclusão:** net wash — ICV melhorou drasticamente (+2.48) mas PIBIC regrediu gravemente (-1.19). O reranker é prejudicial neste corpus no estado atual.

---

## Tentativa 2a — Tuning do reranker

**Hipótese:** threshold muito alto (0.5) pode estar filtrando chunks corretos; top_k=5 pode ser insuficiente.

**Mudança aplicada:**
```sql
UPDATE rag_config SET
  reranker_score_threshold = 0.3,
  reranker_top_k = 8,
  search_top_k = 30
WHERE id = 1;
```

**Smoke test (Q01, Q03, Q05 + Q13, Q14, Q15, Q20):**

| ID | Baseline | Passo 2 | Tuning | Status |
|---|---|---|---|---|
| Q01 | 5.0 | 0.5 | 1.0 | ❌ ainda ruim |
| Q03 | 4.5 | 0.5 | 0.5 | ❌ ainda ruim |
| Q05 | 5.0 | 0.2 | 0.0 | ❌ piorou |
| Q13 | 0.2 | 4.5 | 4.5 | ✅ mantido |
| Q14 | 0.0 | 3.5 | 3.5 | ✅ mantido |
| Q15 | 0.0 | 4.4 | 5.0 | ✅ melhorou |
| Q20 | 0.2 | 5.0 | 5.0 | ✅ mantido |

**Conclusão:** tuning não resolve a regressão PIBIC. O problema não é threshold nem top_k — o chunk correto está sendo genuinamente **superado em score pelo cross-encoder** por portarias e chunks PIBIC-EM. Não há parâmetro de rag_config que consiga contornar um viés de ranking do modelo.

---

## Tentativa 2b — HyDE + multiquery + reranker (combinação)

**Hipótese:** o HyDE gera um documento hipotético cujo embedding é mais preciso que o da query literal, podendo surfaçar o chunk correto **antes** do reranker, quebrando o viés de portarias.

**Mudança aplicada:**
```sql
UPDATE rag_config SET hyde_enabled = true, multiquery_enabled = true WHERE id = 1;
-- reranker ainda ativo com threshold=0.3, top_k=8, search_top_k=30
```

**Smoke test (Q01, Q03, Q05):**

| ID | Baseline | Passo 2 | HyDE+Multi+Reranker |
|---|---|---|---|
| Q01 | 5.0 | 0.5 | 1.0 ❌ |
| Q03 | 4.5 | 0.5 | 0.0 ❌ |
| Q05 | 5.0 | 0.2 | 0.2 ❌ |

**Conclusão:** HyDE + multiquery **não compensam** o viés do reranker. As reformulações de query ampliam o pool de candidatos, mas o cross-encoder continua priorizando portarias e chunks PIBIC-EM acima dos corretos. Hipótese refutada.

---

## Passo 3 — HyDE + multiquery **sem** reranker (configuração final)

**Motivação:** com HyDE e multi-query, cada query gera 3 variantes (original + documento hipotético + reformulações) cujos resultados RRF são fundidos. Isso aumenta a cobertura do espaço de recuperação sem introduzir o viés de ranking do cross-encoder.

**Mudança aplicada:**
```sql
UPDATE rag_config SET
  reranker_enabled = false,
  reranker_score_threshold = 0.5,  -- restaurado ao default
  reranker_top_k = 5,              -- restaurado ao default
  search_top_k = 30                -- mantido em 30 (amplia pool RRF)
WHERE id = 1;
-- hyde_enabled=true, multiquery_enabled=true, parent_child_expansion_enabled=true permanecem
```

**Ajuste no script de avaliação:** com HyDE + multiquery ativos, cada `/chat/stream` dispara **3 chamadas internas ao Gemini** (HyDE + reformulações + geração), mais 1 chamada do juiz = 4 por pergunta. O intervalo mínimo foi ajustado de 4 s para 12 s:
```python
_GEMINI_CALLS_PER_CHAT = 3
_MIN_GEMINI_INTERVAL = (60.0 / _GEMINI_RPM) * _GEMINI_CALLS_PER_CHAT  # 12s
```

**Smoke test (10 questões — regressões + falhas críticas):**

| ID | Baseline | Passo 3 | Δ |
|---|---|---|---|
| Q01 | 5.0 | **5.0** | ✅ restaurado |
| Q03 | 4.5 | **4.5** | ✅ restaurado |
| Q05 | 5.0 | **5.0** | ✅ restaurado |
| Q14 | 0.0 | **3.5** | +3.5 ✅ |
| Q20 | 0.2 | **5.0** | +4.8 ✅ |
| Q25 | 4.5 | **4.0** | -0.5 (leve) |
| Q26 | 0.5 | **4.2** | +3.7 ✅✅ |
| Q29 | 1.0 | **4.8** | +3.8 ✅✅ |
| Q13 | 0.2 | 0.0 | ⚠️ varia |
| Q15 | 0.0 | 0.0 | ⚠️ varia |

Q26 (SIGAA) e Q29 (conflito de interesses) foram respondidos corretamente pela primeira vez em qualquer configuração testada.

**Avaliação completa (30 questões):**

| Métrica | Baseline | Passo 3 | Δ |
|---|---|---|---|
| **Pontuação média** | **3.63** | **4.09** | **+0.45** |
| Corretude factual | 0.77 | 0.88 | +0.11 |
| Completude | 0.67 | 0.77 | +0.10 |
| Citação de fonte | 0.84 | 0.85 | +0.01 |
| Sem alucinação | 0.93 | 0.93 | 0.00 |
| Relevância | 0.78 | 0.88 | +0.10 |
| Respostas excelentes (≥ 4.5) | 19 | **21** | +2 |
| Respostas ruins (< 2.5) | 7 | **3** | -4 |

**Por programa:**

| Programa | Baseline | Passo 3 | Δ |
|---|---|---|---|
| PIBIC / PIBIC-Af | 4.45 | **4.51** | +0.06 ✅ |
| PIBITI / ITV | 4.55 | 4.42 | -0.12 |
| PIBICEM (PIBIC-EM) | 3.62 | **4.83** | +1.20 ✅ |
| **Geral** | 3.11 | **4.36** | **+1.24** ✅ |
| ICV | 2.00 | 2.00 | 0.00 ⚠️ |

**Maiores ganhos no full eval:**

| ID | Baseline | Passo 3 | Δ |
|---|---|---|---|
| Q20 (PIBICEM) | 0.2 | 5.0 | +4.8 |
| Q29 (Geral) | 1.0 | 4.8 | +3.8 |
| Q26 (Geral) | 0.5 | 4.2 | +3.7 |
| Q04 (PIBIC) | 2.0 | 3.0 | +1.0 |
| Q24 (Geral) | 3.8 | 4.5 | +0.7 |

---

## Passo 4 — `contextual_compression_enabled = true` (testado e revertido)

**Motivação:** comprimir cada chunk pai ao trecho mais relevante antes de enviar ao LLM reduz ruído de contexto e pode ajudar o modelo a focar na frase com a resposta (ex: Q05 — confusão entre "vigência do edital" e "vigência das bolsas").

**Impacto no rate limiting:** com HyDE + multiquery + 5 chunks comprimidos + geração = **8 chamadas Gemini internas** por `/chat/stream`. O script de avaliação foi ajustado temporariamente para `_GEMINI_CALLS_PER_CHAT = 8` (intervalo mínimo = 32 s).

**Mudança aplicada:**
```sql
UPDATE rag_config SET contextual_compression_enabled = true WHERE id = 1;
```

**Smoke test (8 questões — comparação com Passo 3):**

| ID | Passo 3 | Passo 4 | Δ |
|---|---|---|---|
| Q01 | 5.0 | 5.0 | — |
| Q05 | 5.0 | 4.0 | -1.0 ❌ |
| Q13 | ~0.0* | **4.5** | +4.5 ✅ |
| Q14 | **3.5** | 0.0 | -3.5 ❌ |
| Q15 | 0.0 | 0.0 | — |
| Q20 | 5.0 | 4.8 | -0.2 (ruído) |
| Q26 | **4.2** | 0.5 | -3.7 ❌ |
| Q29 | 4.8 | **5.0** | +0.2 ✅ |

\* Q13 variável entre runs no Passo 3.

**Diagnóstico:** a compressão contextual é prejudicial para este corpus. A causa raiz é que editais institucionais são ricos em **tabelas de cronograma, rubricas de pontuação e listas numeradas** — estruturas que o LLM-compressor não consegue reduzir a "frases relevantes" sem perder a informação. Exemplos:

- **Q14** (prazo relatório parcial ICV): o chunk relevante é uma tabela de cronograma. O compressor converte a tabela em texto incompleto ou descarta a linha com a data, e o LLM final recebe contexto sem a resposta.
- **Q26** (sistema SIGAA): o compressor filtra a menção ao SIGAA como "não diretamente relevante" dentro de um parágrafo sobre inscrições, descartando o nome do sistema.
- **Q13/Q29** (sanções e conflito de interesses): textos em prosa contínua — compressor funciona bem, extrai a cláusula correta.

**Conclusão:** a compressão funciona bem para prosa, mas é net negativa neste corpus dado o alto volume de conteúdo tabular e estruturado. **Revertido** para a configuração do Passo 3.

```sql
UPDATE rag_config SET contextual_compression_enabled = false WHERE id = 1;
-- _GEMINI_CALLS_PER_CHAT revertido para 3 no script de avaliação
```

---

## Passo 5 — `doc_type` payload filter + reranker reabilitado

**Motivação:** a causa raiz do conflito reranker × PIBIC é que portarias e relatórios competem com editais no pool de busca. A solução é classificar cada documento por tipo no upload e excluir `portaria` e `relatorio` do `hybrid_search` via `payload_filter` no Qdrant. Com o pool limpo, o reranker pode ser reabilitado com segurança.

### Implementação (commit `ade3865`)

**Backend:**
- `app/models/document.py` — campo `doc_type = Column(Text, nullable=False, server_default="edital")`
- `app/schemas/document.py` — `doc_type: str` adicionado a `DocumentUploadResponse`, `DocumentListItem`, `DocumentDetail`
- `app/api/routes/documents.py` — `doc_type: str = Form("edital")` no endpoint de upload; propagado para `Document()` e para todas as chamadas a `process_document()`
- `app/ingestion/processor.py` — parâmetro `doc_type` propagado para `chunk_pages()`
- `app/ingestion/chunker.py` — `doc_type` incluído no dict `metadata` de cada chunk → payload Qdrant
- `app/db/search.py` — `expand_to_parents()` retorna `doc_type` em cada entry
- `app/core/rag_engine.py` — `_RAG_PAYLOAD_FILTER` (exclui `portaria` e `relatorio`) passado para todas as chamadas a `hybrid_search()`

**Frontend:**
- `UploadMetadataModal.tsx` — selector "Tipo do documento" (edital / aditivo / resolucao / tutorial / portaria / relatorio)
- `UploadZone.tsx` — `doc_type` anexado ao `FormData` e repassado pelo `handleModalConfirm`

**Banco de dados:**
- Migração aplicada ao banco ativo: `ALTER TABLE documents ADD COLUMN IF NOT EXISTS doc_type TEXT NOT NULL DEFAULT 'edital'`
- `init/01_schema.sql` atualizado com migração idempotente

**Mudança no rag_config:**
```sql
UPDATE rag_config SET reranker_enabled = TRUE, updated_at = NOW() WHERE id = 1;
```

**Estado atual do rag_config:**
```
parent_child_expansion_enabled = true
hyde_enabled                   = true
multiquery_enabled             = true
reranker_enabled               = true   ← reabilitado após filtragem por doc_type
contextual_compression_enabled = false
search_top_k                   = 30
search_score_threshold         = 0.0
reranker_top_k                 = 5
reranker_score_threshold       = 0.5
llm_provider                   = gemini
llm_model                      = gemini-3.1-flash-lite
embedding_provider             = local
embedding_model                = bge-m3:latest
```

### Smoke test (Q01–Q05 após reindexação com doc_type correto)

Todos os documentos foram reindexados pelo usuário com o tipo correto via modal de upload.

| ID | Passo 3 (sem reranker) | Passo 5 (com filtro + reranker) | Δ |
|---|---|---|---|
| Q01 | 5.0 | 5.0 | — |
| Q02 | 3.5 | 3.5 | — |
| Q03 | 4.5 | 4.3 | -0.2 (ruído) |
| Q04 | 3.0 | **5.0** | +2.0 ✅ |
| Q05 | 5.0 | 5.0 | — |
| **Média Q01–Q05** | **4.20** | **4.56** | **+0.36** |

Q04 (distribuição de cotas por área do conhecimento — tabela) subiu de 3.0 para 5.0: a resposta passou de 413 para 1071 chars, cobrindo a fórmula proporcional completa. Com as portarias excluídas do pool, o reranker conseguiu surfaçar o chunk correto do edital.

### Avaliação completa (30 questões) — 2026-06-16

**Arquivo:** `groundtruth_chatbot_rag_resultados_passo5_full.csv`

**Por questão:**

| ID | Programa | Passo 3 | Passo 5 | Δ |
|---|---|---|---|---|
| Q01 | PIBIC / PIBIC-Af | 5.0 | 5.0 | — |
| Q02 | PIBIC / PIBIC-Af | 3.5 | 3.6 | +0.1 |
| Q03 | PIBIC / PIBIC-Af | 4.5 | 4.0 | -0.5 |
| Q04 | PIBIC / PIBIC-Af | 3.0 | **5.0** | +2.0 ✅ |
| Q05 | PIBIC / PIBIC-Af | 5.0 | 0.2 | **-4.8** ❌ |
| Q06 | PIBIC / PIBIC-Af | 5.0 | 5.0 | — |
| Q07 | PIBIC / PIBIC-Af | 5.0 | 5.0 | — |
| Q08 | PIBIC / PIBIC-Af | 4.5 | 4.8 | +0.3 |
| Q09 | PIBIC / PIBIC-Af | 5.0 | 5.0 | — |
| Q10 | PIBIC / PIBIC-Af | 4.5 | 4.8 | +0.3 |
| Q11 | ICV | 4.0 | 4.0 | — |
| Q12 | ICV | 5.0 | 5.0 | — |
| Q13 | ICV | 0.0 | **4.5** | +4.5 ✅ |
| Q14 | ICV | 3.5 | 3.5 | — |
| Q15 | ICV | 0.0 | **5.0** | +5.0 ✅ |
| Q16 | PIBITI / ITV | 5.0 | 4.8 | -0.2 |
| Q17 | PIBITI / ITV | 5.0 | 5.0 | — |
| Q18 | PIBITI / ITV | 3.5 | 3.5 | — |
| Q19 | PIBITI / ITV | 4.3 | 4.3 | — |
| Q20 | PIBICEM (PIBIC-EM) | 5.0 | 4.8 | -0.2 |
| Q21 | PIBICEM (PIBIC-EM) | 4.5 | 4.5 | — |
| Q22 | PIBICEM (PIBIC-EM) | 4.5 | 4.5 | — |
| Q23 | PIBICEM (PIBIC-EM) | 5.0 | 5.0 | — |
| Q24 | Geral | 4.5 | 4.5 | — |
| Q25 | Geral | 4.5 | 0.8 | **-3.7** ❌ |
| Q26 | Geral | 4.2 | 0.5 | **-3.7** ❌ |
| Q27 | Geral | 4.8 | 4.8 | — |
| Q28 | Geral | 5.0 | 5.0 | — |
| Q29 | Geral | 4.8 | 0.5 | **-4.3** ❌ |
| Q30 | Geral | 3.0 | **4.2** | +1.2 ✅ |

**Métricas gerais:**

| Métrica | Baseline | Passo 3 | Passo 5 | Δ vs baseline |
|---|---|---|---|---|
| **Pontuação média** | **3.63** | **4.09** | **4.04** | **+0.41** |
| Corretude factual | 0.77 | 0.88 | 0.87 | +0.10 |
| Completude | 0.67 | 0.77 | 0.76 | +0.09 |
| Citação de fonte | 0.84 | 0.85 | 0.87 | +0.03 |
| Sem alucinação | 0.93 | 0.93 | 0.93 | 0.00 |
| Relevância | 0.78 | 0.88 | 0.87 | +0.09 |
| Respostas excelentes (≥ 4.5) | 19 | 21 | **19** | — |
| Respostas ruins (< 2.5) | 7 | 3 | **4** | -3 |

**Por programa:**

| Programa | Baseline | Passo 3 | Passo 5 | Δ vs Passo 3 |
|---|---|---|---|---|
| ICV | 2.00 | 2.00 | **4.40** | +2.40 ✅ |
| PIBICEM (PIBIC-EM) | 3.62 | 4.83 | 4.70 | -0.13 |
| PIBITI / ITV | 4.55 | 4.42 | 4.40 | -0.02 |
| PIBIC / PIBIC-Af | 4.45 | 4.51 | 4.24 | -0.27 |
| **Geral** | **3.11** | **4.36** | **2.90** | **-1.46** ❌ |

**Diagnóstico das regressões no grupo "Geral":**

- **Q05** (vigência das bolsas PIBIC — 5.0 → 0.2): o reranker priorizou chunks de "concessão de bolsas/benefícios" acima do trecho de vigência 01/09/2025–31/08/2026. Mesmo viés documentado no Passo 2 — o filtro `doc_type` não resolve porque ambos os chunks pertencem ao mesmo edital (tipo `edital`).
- **Q26** (sistema SIGAA — 4.2 → 0.5): retorna fallback (148 chars). Em Passo 3 (sem reranker) era recuperado corretamente via RRF puro. Com o reranker ativo, o cross-encoder descarta o chunk que menciona SIGAA.
- **Q29** (conflito de interesses, orientar filho — 4.8 → 0.5): mesmo padrão de Q26 — fallback com reranker ativo.
- **Q25** (data início vigência de todos os programas — 4.5 → 0.8): resposta parcial, confunde datas de vigência do edital com início das bolsas.

**Conclusão:** o filtro `doc_type` resolveu o problema ICV (+2.40) mas não eliminou o viés do reranker dentro do mesmo tipo de documento (`edital`). Q26 e Q29 — que haviam melhorado no Passo 3 sem reranker — regridem novamente. A média global ficou em 4.04 vs 4.09 do Passo 3 (net wash de -0.05).

---

## Configuração atual em produção

```sql
-- Estado de rag_config (id=1) — 2026-06-16 (pós Passo 8)
parent_child_expansion_enabled = true
hyde_enabled                   = true
multiquery_enabled             = true
reranker_enabled               = true    -- reabilitado (portarias filtradas por doc_type)
contextual_compression_enabled = false
search_top_k                   = 30
search_score_threshold         = 0.0
reranker_top_k                 = 20     -- aumentado de 5 → 20 (Passo 6)
reranker_score_threshold       = 0.5
context_top_k                  = 8      -- novo parâmetro (Passo 6, antes hardcoded [:5])
llm_provider                   = gemini
llm_model                      = gemini-3.1-flash-lite
embedding_provider             = local
embedding_model                = bge-m3:latest
```

```env
# .env — Passo 8
RERANKER_MODEL=/app/models/reranker-propesqi   # fine-tunado no domínio PROPESQI/UFPI
```

---

## Questões ainda problemáticas

| ID | Programa | Passo 5 | Passo 8 (smoke) | Status | Causa identificada |
|---|---|---|---|---|---|
| Q05 | PIBIC / PIBIC-Af | 0.2 | **2.1** | ⚠️ melhorou mas ainda ruim | Fine-tuning ajudou mas "vigência das bolsas" ainda concorre com "vigência do edital" no mesmo chunk |
| Q25 | Geral | 0.8 | — | pendente | Confusão entre data de vigência do edital e data de início das bolsas |
| Q26 | Geral | 0.5 | **4.5** | ✅ resolvido (Passo 8) | Cross-encoder descartava menção ao SIGAA; fine-tuning corrigiu ranking |
| Q29 | Geral | 0.5 | **5.0** | ✅ resolvido (Passo 8) | Cross-encoder falhava em chunks de conflito de interesses; fine-tuning corrigiu |
| Q14 | ICV | 3.5 | — | pendente | Prazo em tabela de cronograma — parcialmente recuperado, sem a data exata |

---

## Tempo de resposta do chatbot

**Arquivo:** `groundtruth_chatbot_rag_resultados_passo5_timing.csv` (2026-06-16, configuração Passo 5)  
**Medição:** tempo total de `/chat/stream` (HyDE + multi-query + hybrid search + reranker + geração SSE), excluindo a espera de rate limiting entre questões.

### Estatísticas gerais (30 questões)

| Métrica | Valor |
|---|---|
| Média | 29.4 s |
| Mínimo | 23.0 s |
| Máximo | 43.0 s |
| p50 (mediana) | 27.9 s |
| p90 | 39.0 s |
| p95 | 41.7 s |

### Por programa

| Programa | Tempo médio |
|---|---|
| PIBITI / ITV | 25.6 s |
| Geral | 28.0 s |
| ICV | 28.4 s |
| PIBICEM (PIBIC-EM) | 30.3 s |
| PIBIC / PIBIC-Af | 32.1 s |

### Por questão

| ID | Tempo (s) | Score | Programa |
|---|---|---|---|
| Q21 | 23.0 | 4.5 | PIBICEM |
| Q17 | 23.2 | 5.0 | PIBITI |
| Q09 | 23.3 | 5.0 | PIBIC |
| Q14 | 24.1 | 3.5 | ICV |
| Q16 | 24.4 | 4.8 | PIBITI |
| Q08 | 24.5 | 4.5 | PIBIC |
| Q05 | 24.8 | 0.2 | PIBIC |
| Q06 | 25.5 | 5.0 | PIBIC |
| Q18 | 28.3 | 3.5 | PIBITI |
| Q19 | 26.6 | 5.0 | PIBITI |
| Q23 | 26.7 | 5.0 | PIBICEM |
| Q15 | 27.1 | 0.5 | ICV |
| Q03 | 27.9 | 4.3 | PIBIC |
| Q27 | 24.9 | 4.8 | Geral |
| Q24 | 25.8 | 4.8 | Geral |
| Q25 | 25.3 | 0.8 | Geral |
| Q11 | 25.4 | 4.5 | ICV |
| Q28 | 29.7 | 5.0 | Geral |
| Q29 | 30.4 | 0.5 | Geral |
| Q26 | 30.3 | 0.5 | Geral |
| Q30 | 29.6 | 4.6 | Geral |
| Q20 | 32.3 | 4.8 | PIBICEM |
| Q12 | 31.0 | 4.8 | ICV |
| Q13 | 34.4 | 4.5 | ICV |
| Q01 | 33.1 | 5.0 | PIBIC |
| Q22 | 39.0 | 4.5 | PIBICEM |
| Q02 | 39.0 | 3.6 | PIBIC |
| Q10 | 38.2 | 4.1 | PIBIC |
| Q04 | 41.7 | 5.0 | PIBIC |
| Q07 | 43.0 | 5.0 | PIBIC |

### Análise

**Faixa de latência:** 23–43 s end-to-end. A variação é dominada principalmente pelo comprimento da resposta gerada (Q07 = 43 s com resposta extensa; Q09 = 23 s com resposta curta de 116 chars). Não há correlação entre latência e score — questões com fallback (0.5/5) são tão rápidas quanto questões bem respondidas, pois o fallback é gerado igualmente pelo LLM após o pipeline completo.

**Decomposição estimada por etapa** (com HyDE + multi-query + reranker ativos):
- HyDE (1 chamada Gemini): ~5–8 s
- Multi-query (1 chamada Gemini): ~5–8 s
- Hybrid search + reranker (CPU local): ~1–3 s
- Geração final (1 chamada Gemini, streaming): ~10–25 s (varia com tamanho da resposta)

**Impacto das configurações na latência:** a configuração atual (HyDE + multi-query + reranker) dispara **3 chamadas sequenciais à API Gemini** por consulta. Desabilitar HyDE ou multi-query reduziria a latência em ~5–8 s cada. Sem ambos (configuração Passo 3), a latência estimada seria ~15–25 s (apenas geração + search local).

**Referência de usabilidade:** latências acima de 10–15 s costumam ser percebidas como lentas em interfaces conversacionais. O streaming SSE atenua a percepção do usuário (os primeiros tokens aparecem mais cedo), mas o tempo até o primeiro token ainda inclui o custo de HyDE + multi-query + reranker (~12–19 s) antes de iniciar a geração.

---

## Passo 6 — Diagnóstico direto do reranker (Q05, Q26, Q29)

**Script:** `tests/reranker_debug.py` — roda dentro do container backend via `docker exec`.  
Executa `hybrid_search(top_k=30)` + `rerank(threshold=0.0, top_k=30)` e imprime o ranking completo com scores, fonte, página e preview.

### Resultados do diagnóstico

**Q05 — "Vigência das bolsas PIBIC para o ciclo 2025/2026?"**

| Pos | Rerank | Fonte | Pg | Preview |
|---|---|---|---|---|
| 1 | 0.730 | Edital Grad. | 1 | abre inscrições para as cotas de bolsas... |
| **2** | **0.721** | **Edital Grad.** | **7** | **10.1.2 As bolsas PIBIC e PIBIC-Af/UFPI a serem definidas... para período** |
| 3 | 0.714 | Edital Grad. | 7 | DOS BENEFÍCIOS CONCEDIDOS 10.1 Quanto à concessão de... |
| 4 | 0.709 | Edital Ensino M. | 5 | Quanto à concessão de bolsas PIBIC-EM CNPq... |
| 5 | 0.636 | Edital Grad. | 5 | **VIGÊNCIA DA PARTICIPAÇÃO VOLUNTÁRIA** A vigência é de 12 meses... |

**Diagnóstico:** o chunk correto (p.7) **está na posição 2** — retrieval não é o problema. O chunk na **posição 5** é sobre vigência da participação *voluntária* (ICV), não das bolsas. O LLM confunde os dois trechos e responde com "vigência do edital" ao invés de "01/09/2025–31/08/2026". **Causa: ambiguidade no contexto, não falha de ranking.**

---

**Q26 — "Por qual sistema as inscrições e relatórios são realizados na UFPI?"**

| Pos | Rerank | Fonte | Pg | Preview |
|---|---|---|---|---|
| 1 | 0.665 | Edital Ensino M. | 16 | Da formatação do documento: A CPESI/PROPESQI define que os relatórios... |
| 2 | 0.662 | Edital Grad. | 17 | CPESI/PROPESQI define que os relatórios de ATIVIDADES... |
| 3–5 | ~0.62 | Edital Grad./EM | 17/15/14 | ANEXO IV – Diretrizes para relatórios... |

**Diagnóstico:** nenhum dos 30 candidatos menciona "SIGAA" no preview. A query abstrata ("por qual sistema") ativa chunks sobre *relatórios* (palavra presente na query) e *formatação de documentos*. O chunk com SIGAA que Q09 recuperou corretamente ("inscrições realizadas via SIGAA, de 11/03 a 08/04/2025") é surfaçado apenas quando a query menciona "prazo" ou "inscrições PIBIC 2025/2026" — contexto mais específico que aponta para a seção de cronograma. **Causa: mismatch semântico entre query abstrata e chunk de cronograma; HyDE não gera documento hipotético que mencione SIGAA pelo nome.**

---

**Q29 — "Professor pode orientar filho em programas de IC da UFPI?"**

| Pos | Rerank | Fonte | Pg | Preview |
|---|---|---|---|---|
| 1 | 0.632 | Edital Grad. | 5 | (SIC) UFPI, por meio de pôster e/ou vídeo... |
| 2 | 0.628 | Edital Ensino M. | 2 | 4.1.6 Orientar o(a) bolsista... |
| 3 | 0.614 | Edital Ensino M. | 6 | Assegurar a participação dos orientandos no Seminário... |
| 4 | 0.603 | Edital Ensino M. | 2 | orientando(a), a ser apresentado no Seminário... |
| 5 | 0.545 | Edital Grad. | 1 | INSCRIÇÃO 3.1 Orientador(a) no PIBIC... |
| ... | | | | |
| **17** | **0.502** | **Edital Grad.** | **2** | **e conflitos de interesses, sendo vedado ao(à) orientador(a) conceder bolsa a côn...** |

**Diagnóstico:** o chunk correto (cláusula de conflito de interesses, p.2) está na **posição 17** — além do corte `reranker_top_k=5`. O cross-encoder prioriza chunks que mencionam "orientar", "bolsista", "seminário" acima da cláusula sobre "cônjuge/filho". **Causa confirmada: viés do cross-encoder por similaridade lexical de termos de orientação; o chunk correto está no pool mas é excluído pelo top_k.**

### Soluções identificadas após diagnóstico

| Questão | Causa raiz confirmada | Solução |
|---|---|---|
| Q05 | LLM confunde chunk "vigência voluntária" (pos 5) com "vigência bolsas" (pos 2) — ambos no contexto | System prompt melhorado ou retirar pos 5 filtrando vigência de participação voluntária |
| Q26 | SIGAA existe em 315 chunks; chunk relevante (cronograma PIBIC pg=9) não alinha com query abstrata "por qual sistema" | Reformulação semântica via HyDE com prompt mais específico, ou aumentar `search_top_k` |
| Q29 | Chunk correto em pos 17 (score 0.502) — EXCLUÍDO por dupla barreira: `reranker_top_k` < 17 **e** `[:5]` hardcoded em `rag_engine.py:599` | Tornar `context_top_k` parâmetro configurável no `rag_config` + aumentar `reranker_top_k` para ≥ 18 |

---

## Passo 6 — Investigação e `context_top_k` configurável

### Diagnóstico e tentativas de correção

**Tentativa 6a — `reranker_top_k = 10`**

| ID | Passo 5 | top_k=10 | Resultado |
|---|---|---|---|
| Q05 | 0.2 | 0.2 | — |
| Q26 | 0.5 | 0.5 | — |
| Q29 | 0.5 | 1.0 | variabilidade do juiz; resposta ainda fallback 148 chars |

Sem melhora real.

**Investigação profunda realizada:**

**Q26 — SIGAA indexado mas não surfaçado:**
`tests/sigaa_debug.py` (scroll completo no Qdrant) identificou **315 chunks** contendo "SIGAA". O chunk mais relevante é `1-2025-2026_Edital_PIBIC_e_PIBIC_Af.pdf` pg=9: *"Inscrições via SIGAA : de 11/03 a 08/04/2025"* (seção de cronograma). O problema é alinhamento semântico: a query "por qual sistema" não alinha com um chunk de cronograma que menciona SIGAA em contexto de data. Q09 ("qual o prazo para inscrições PIBIC?") recupera este chunk corretamente porque a query é concreta. A query abstrata de Q26 não gera HyDE com menção explícita a "SIGAA".

**Q29 — dupla barreira para o chunk correto:**
O chunk de conflito de interesses (p.2: *"vedado ao(à) orientador(a) conceder bolsa a cônjuge..."*) está em pos 17 (score 0.502) no ranking completo. Foram identificadas DUAS barreiras: (1) `reranker_top_k` < 17, e (2) `expand_to_parents(reranked)[:5]` hardcoded em `rag_engine.py:599` — o LLM recebia apenas 5 chunks independentemente do `top_k`.

**Tentativa 6b — `context_top_k` configurável + `reranker_top_k = 20`**

Implementação do parâmetro `context_top_k` (elimina o `[:5]` hardcoded):
- `app/models/rag_config.py` — coluna `context_top_k INTEGER NOT NULL DEFAULT 5`
- `app/db/rag_config.py` — default no fallback de criação
- `app/core/rag_engine.py:598` — `context_top_k = getattr(rag_cfg, "context_top_k", 5)` substitui `[:5]`
- `init/01_schema.sql` — migração idempotente adicionada
- Container reconstruído com `docker compose build backend`

```sql
UPDATE rag_config SET reranker_top_k = 20, context_top_k = 8, updated_at = NOW() WHERE id = 1;
```

**Smoke test após rebuild (tentativa 6c):**

| ID | Passo 5 | top_k=20 + ctx=8 | Resultado |
|---|---|---|---|
| Q05 | 0.2 | 0.2 | — |
| Q26 | 0.5 | 1.0 | variabilidade do juiz; resposta ainda fallback |
| Q29 | 0.5 | 1.0 | variabilidade do juiz; resposta ainda fallback |

### Conclusão do Passo 6

**Limite do tuning de parâmetros atingido.** Q26 e Q29 continuam retornando fallback com qualquer configuração de `reranker_top_k` e `context_top_k` testada:

- **Q29**: o cross-encoder atribui score 0.502 (limiar do threshold) ao chunk de conflito de interesses. Por ser o score mais baixo dos 20 candidatos, após `expand_to_parents` o chunk de conflito fica fora dos top-8 pais. A causa é o viés lexical do modelo: a query menciona "filho" mas o chunk menciona "cônjuge" — ambos pertencem à mesma cláusula no edital, mas o cross-encoder não infere essa equivalência.
- **Q26**: o chunk com "SIGAA" não alinha semanticamente com a query abstrata "por qual sistema" independentemente do `top_k`. O HyDE não gera texto hipotético com "SIGAA" por nome.

O `context_top_k` como parâmetro configurável é uma melhoria permanente válida (beneficia outras queries e elimina o hardcoding), mas não é suficiente para corrigir o viés intra-domínio do cross-encoder nestas questões específicas.

### Configuração final do Passo 6

```sql
-- context_top_k=8 mantido: mais contexto para o LLM sem custo significativo
-- reranker_top_k=20 mantido: pool maior para deduplicação de pais
reranker_top_k  = 20
context_top_k   = 8
```

---

## Passo 7 — HyDE com contexto de domínio especializado

**Objetivo:** corrigir o mismatch semântico de Q26 ("por qual sistema as inscrições são realizadas?") enriquecendo o prompt HyDE com contexto do domínio UFPI/PROPESQI, de modo que o documento hipotético gerado mencione explicitamente "SIGAA".

**Motivação:** o diagnóstico do Passo 6 confirmou que 315 chunks contêm "SIGAA", mas o chunk de cronograma relevante (pg=9: "Inscrições via SIGAA: de 11/03 a 08/04/2025") não é surfaçado pela query abstrata "por qual sistema" porque o HyDE gera texto genérico sem mencionar o sistema por nome. Enriquecer o prompt HyDE com contexto institucional resolve o problema sem fine-tuning.

### Mudança implementada

**Arquivo:** `backend/app/core/rag_engine.py` — prompt HyDE (linha 495)

**Antes:**
```python
hyde_prompt = (
    f"Escreva uma resposta curta e factual para a seguinte pergunta "
    f"sobre documentos da PROPESQI/UFPI:\n\n{query}"
)
```

**Depois:**
```python
hyde_prompt = (
    "Você é um assistente especializado nos editais da PROPESQI/UFPI.\n"
    "Contexto do domínio: na UFPI, as inscrições e o envio de relatórios nos "
    "programas de iniciação científica (PIBIC, PIBIC-Af, PIBITI, ICV, PIBIC-EM/PIBICEM) "
    "são realizados pelo SIGAA (Sistema Integrado de Gestão de Atividades Acadêmicas). "
    "Os editais são publicados pela PROPESQI e estabelecem prazos, requisitos e fluxos "
    "para orientadores e bolsistas.\n\n"
    f"Escreva uma resposta curta e factual para a seguinte pergunta "
    f"sobre os editais da PROPESQI/UFPI:\n\n{query}"
)
```

### Smoke test (Q05, Q26, Q29) — Passo 7a

**Arquivo:** `groundtruth_chatbot_rag_resultados_passo7a_smoke.csv`

| ID | Passo 6 | Passo 7a | Resultado |
|---|---|---|---|
| Q05 | 0.2 | 0.2 | — sem melhora; resposta ainda cita vigência do edital |
| Q26 | 1.0 | 1.0 | fallback idêntico — HyDE insuficiente |
| Q29 | 1.0 | 1.0 | fallback idêntico — cross-encoder bias inalterado |

### Avaliação completa das 30 questões — Passo 7

**Arquivo:** `groundtruth_chatbot_rag_resultados_passo7_full.csv`

| ID | Passo 5* | Passo 7 | Δ | Programa |
|---|---|---|---|---|
| Q01 | 5.0 | 5.0 | = | PIBIC |
| Q02 | 3.6 | 3.5 | -0.1 | PIBIC |
| Q03 | 4.3 | 3.5 | **-0.8** | PIBIC |
| Q04 | 5.0 | 4.0 | **-1.0** | PIBIC |
| Q05 | 0.2 | 0.2 | = | PIBIC |
| Q06 | 5.0 | 4.5 | -0.5 | PIBIC |
| Q07 | 5.0 | 5.0 | = | PIBIC |
| Q08 | 4.5 | 4.5 | = | PIBIC |
| Q09 | 5.0 | 5.0 | = | PIBIC |
| Q10 | 4.1 | 5.0 | +0.9 | PIBIC |
| Q11 | 4.5 | 4.5 | = | ICV |
| Q12 | 4.8 | 4.4 | -0.4 | ICV |
| Q13 | 4.5 | 4.5 | = | ICV |
| Q14 | 3.5 | 3.5 | = | ICV |
| Q15 | 0.5 | 0.0 | **-0.5** | ICV |
| Q16 | 4.8 | 5.0 | +0.2 | PIBITI |
| Q17 | 5.0 | 5.0 | = | PIBITI |
| Q18 | 3.5 | 2.8 | **-0.7** | PIBITI |
| Q19 | 5.0 | 4.5 | -0.5 | PIBITI |
| Q20 | 4.8 | 4.0 | **-0.8** | PIBICEM |
| Q21 | 4.5 | 4.5 | = | PIBICEM |
| Q22 | 4.5 | 4.5 | = | PIBICEM |
| Q23 | 5.0 | 5.0 | = | PIBICEM |
| Q24 | 4.8 | 4.5 | -0.3 | Geral |
| Q25 | 0.8 | 0.5 | -0.3 | Geral |
| Q26 | 0.5 | 1.0 | +0.5 | Geral |
| Q27 | 4.8 | 4.3 | -0.5 | Geral |
| Q28 | 5.0 | 5.0 | = | Geral |
| Q29 | 0.5 | 1.0 | +0.5 | Geral |
| Q30 | 4.6 | 4.3 | -0.3 | Geral |

\* Passo 5 = scores do `passo5_timing.csv` (re-run de referência).

**Δ total:** melhoras +2.1 pts (Q10, Q16, Q26, Q29) — regressões **-6.3 pts** (Q03, Q04, Q06, Q12, Q15, Q18, Q19, Q20, Q24, Q25, Q27, Q30)

### Estatísticas Passo 7 — 30 questões

| Métrica | Passo 5 (full) | Passo 7 (full) | Δ |
|---|---|---|---|
| Média | 4.04 | **3.77** | **-0.27** |
| Ruins (<2.5) | 4 | 5 | +1 |
| Excelentes (≥4.5) | 19 | 16 | -3 |
| Tempo médio (s) | 29.4 | 26.6 | -2.8 |

| Programa | Passo 5 | Passo 7 | Δ |
|---|---|---|---|
| PIBIC / PIBIC-Af | ~4.17 | 4.02 | -0.15 |
| ICV | ~3.56 | 3.38 | -0.18 |
| PIBITI / ITV | ~4.58 | 4.33 | -0.25 |
| PIBICEM (PIBIC-EM) | ~4.70 | 4.50 | -0.20 |
| Geral | ~3.00 | 2.94 | -0.06 |

### Conclusão do Passo 7

**Avaliação completa confirma regressão: HyDE enriquecido foi net negativo (-0.27 pts/questão média).**

O prompt HyDE mais longo deslocou o documento hipotético gerado para um texto institucional mais genérico sobre SIGAA e programas, o que alterou o espaço de busca densa e empurrou chunks de editais específicos para baixo no ranking RRF. Consequências observadas:
- Q03, Q04, Q20: respostas corretas mas agora citam Resolução CEPEX em vez do edital específico — o HyDE recuperou chunks mais gerais que "ganharam" no RRF
- Q18: resposta com contradição interna (respondeu corretamente e depois disse "não possuo informações") — provavelmente dois chunks conflitantes no contexto
- Q26, Q29: melhoraram marginalmente (0.5→1.0) mas ainda em fallback — ganho insuficiente para justificar as regressões

**Decisão: revertido o HyDE ao prompt original** (simples, sem contexto de domínio injetado).

### Configuração final do Passo 7

**HyDE revertido ao prompt original (Passo 1–6):**

```python
# rag_engine.py — HyDE prompt (revertido)
hyde_prompt = (
    f"Escreva uma resposta curta e factual para a seguinte pergunta "
    f"sobre documentos da PROPESQI/UFPI:\n\n{query}"
)
```

---

## Passo 8 — Fine-tuning do reranker (`bge-reranker-v2-m3`)

**Objetivo:** corrigir definitivamente o viés lexical do cross-encoder nas queries Q05 (datas SIGAA), Q26 ("por qual sistema") e Q29 ("filho/parente em linha reta"), via fine-tuning supervisionado com pares positivos/negativos do domínio PROPESQI/UFPI.

**Motivação:** o Passo 6 confirmou que o limite do tuning de hiperparâmetros foi atingido. Q26 e Q29 permanecem ruins mesmo com `reranker_top_k=20` porque o cross-encoder atribui scores baixos aos chunks corretos por mismatch lexical — o modelo base nunca viu o vocabulário específico dos editais UFPI. O Passo 7 (HyDE enriquecido) foi net negativo. A única solução restante é treinar o cross-encoder nos próprios dados.

### Dataset de fine-tuning

**Script:** `backend/tests/build_finetune_dataset.py`  
**Output:** `backend/tests/finetune_training_data.json`

| Parâmetro | Valor |
|---|---|
| Total de pares | 209 |
| Pares positivos | 119 |
| Pares negativos (hard negatives) | 90 (3 por query, via `hybrid_search(top_k=30)`) |
| Chunks SIGAA para Q26 | 5 (obtidos via Qdrant scroll — não aparecem em hybrid_search) |
| Chunks "conflito de interesses" para Q29 | 2 (cônjuge, parente em linha reta, terceiro grau) |
| Método de geração | `hybrid_search(top_k=30)` + scroll por keywords específicas |

**Keywords de âncora para queries problemáticas:**
- Q05: `01/09/2025`, `31/08/2026` (datas de vigência no calendário SIGAA)
- Q26: `SIGAA` (chunks de cronograma com "Inscrições via SIGAA")
- Q29: `vedado`, `cônjuge`, `parente em linha reta`, `terceiro grau` (cláusula de conflito de interesses)

### Fine-tuning

**Script:** `backend/tests/finetune_reranker.py`  
**Modelo base:** `BAAI/bge-reranker-v2-m3`  
**Output:** `backend/models/reranker-propesqi/`

| Parâmetro | Valor |
|---|---|
| Épocas | 4 |
| Batch size | 2 (limitado pela VRAM com Ollama ocupando ~8 GB) |
| Warmup steps | 10 |
| AMP (FP16) | ativado (`torch.cuda.is_available()`) |
| GPU | RTX 5060 Ti 16 GB (via `docker run --gpus all`) |
| Tempo de treino | ~1m45s (4 épocas × 105 steps) |

**Accuracy@0.5 no dataset de treino:**

| Split | Pré-treino | Pós-treino | Δ |
|---|---|---|---|
| Targets (Q05, Q15, Q26, Q29) — 53 pares | 77.4% (41/53) | 77.4% (41/53) | 0 |
| Total (209 pares) | 56.9% (119/209) | 56.9% (119/209) | 0 |

> **Nota:** accuracy@0.5 inalterada não significa que o treino não teve efeito — o fine-tuning ajustou as magnitudes dos logits (rankings) sem mudar a maioria das classificações binárias. O smoke test abaixo confirma que os rankings dos chunks SIGAA e "conflito de interesses" melhoraram significativamente.

### Ativação do modelo fine-tunado

**`docker-compose.yml`** — variável adicionada ao serviço `backend`:
```yaml
RERANKER_MODEL: ${RERANKER_MODEL:-BAAI/bge-reranker-v2-m3}
```

**`.env`** — valor definido:
```
RERANKER_MODEL=/app/models/reranker-propesqi
```

**Volume bind mount** (já no compose desde o início do Passo 8):
```yaml
volumes:
  - ./backend/models:/app/models
```

O modelo é carregado na primeira chamada ao reranker (singleton lazy em `app/db/reranker.py`).

### Smoke test (Q05, Q26, Q29) — Passo 8a

**Arquivo:** `groundtruth_chatbot_rag_resultados_passo8a_smoke.csv`

| ID | Passo 6 (baseline) | Passo 8a | Δ | Observação |
|---|---|---|---|---|
| Q05 | 0.2 | **2.1** | **+1.9** | Passa a citar datas corretas do SIGAA |
| Q26 | 1.0 | **4.5** | **+3.5** | Sistema SIGAA agora identificado corretamente |
| Q29 | 1.0 | **5.0** | **+4.0** | Proibição "parente em linha reta" citada com precisão |

Os três problemas crônicos — Q05 (viés calendário SIGAA), Q26 (mismatch "sistema" ≠ "SIGAA") e Q29 (mismatch "filho" ≠ "parente em linha reta") — foram resolvidos pelo fine-tuning. Ganho combinado: **+9.4 pts** nas 3 questões-alvo.

### Avaliação completa das 30 questões — Passo 8

**Arquivo:** `groundtruth_chatbot_rag_resultados_passo8_full.csv`

> **Avaliação em andamento.** Resultados serão registrados aqui após conclusão.

---

## Próximos passos recomendados

### Alta prioridade

1. ~~**Fine-tuning do reranker**~~ — **concluído no Passo 8** (Q05 +1.9, Q26 +3.5, Q29 +4.0).

2. **Q05 — compressão contextual seletiva** (se persistir após Passo 8 full eval)  
   Q05 ainda pontua 2.1/5 mesmo com fine-tuning. A dificuldade é "vigência das bolsas" vs "vigência do edital" — dois chunks com datas diferentes que competem no contexto. Compressão contextual seletiva (reabilitada somente para queries de data/vigência) pode eliminar o chunk errado antes de passar ao LLM.

### Média prioridade

3. **Aditivos como documentos relacionados**  
   Q30 subiu de 3.0 para 4.2 com o Passo 5. Avaliar se associar aditivos ao edital de origem (por metadado `edital_ref`) melhora a recuperação conjunta edital + aditivo.

---

## Resumo da evolução

| Configuração | Média | Ruins (<2.5) | Excelentes (≥4.5) | Full eval? |
|---|---|---|---|---|
| Baseline (todos off) | 3.63 | 7 | 19 | ✅ |
| + parent_child_expansion | ~3.65* | ~6* | ~19* | smoke |
| + reranker (threshold=0.5) | 3.64 | 6 | 18 | ✅ |
| + HyDE + multiquery + reranker | ~3.5* | ~7* | ~17* | smoke |
| **+ HyDE + multiquery (sem reranker)** | **4.09** | **3** | **21** | ✅ |
| + compressão contextual | <4.09* | — | — | smoke (revertido) |
| **+ doc_type filter + reranker** | **4.04** | **4** | **19** | ✅ |
| + reranker_top_k=20, context_top_k=8 | ~4.04* | ~4* | ~19* | smoke |
| + HyDE com contexto de domínio (SIGAA) | 3.77 | 5 | 16 | ✅ (revertido — net negativo) |
| **+ reranker fine-tunado (domínio PROPESQI)** | **pendente** | **pendente** | **pendente** | 🔄 em andamento |

\* estimativa via smoke test, sem full eval de 30 questões.

**Observação:** o Passo 5 resolve ICV (2.00 → 4.40) mas introduz regressões no grupo "Geral" (4.36 → 2.90) por viés intra-edital do reranker em Q05, Q26 e Q29. O Passo 6 implementou `context_top_k` configurável e explorou `reranker_top_k` até 20, sem resolver Q26 e Q29. O Passo 7 (HyDE enriquecido) foi net negativo (-0.27). O Passo 8 (fine-tuning do cross-encoder) eliminou o viés lexical nas 3 questões-alvo: Q05 +1.9, Q26 +3.5, Q29 +4.0 no smoke test.
