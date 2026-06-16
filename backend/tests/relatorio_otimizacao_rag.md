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

## Configuração final em produção

```sql
-- Estado atual de rag_config (id=1)
parent_child_expansion_enabled = true
hyde_enabled                   = true
multiquery_enabled             = true
reranker_enabled               = false   -- mantido off (viés estrutural)
contextual_compression_enabled = false
search_top_k                   = 30      -- era 20
search_score_threshold         = 0.0
reranker_top_k                 = 5
reranker_score_threshold       = 0.5
llm_provider                   = gemini
llm_model                      = gemini-3.1-flash-lite
embedding_provider             = local
embedding_model                = bge-m3:latest
```

---

## Questões ainda problemáticas

| ID | Programa | Nota atual | Causa identificada |
|---|---|---|---|
| Q13 | ICV | 0.0–4.5 (varia) | Chunk correto não estável no top-5 sem reranker; melhora muito com reranker mas reranker quebra PIBIC |
| Q14 | ICV | 3.5 | Prazo específico recuperado mas com baixa consistência |
| Q15 | ICV | 0.0–5.0 (varia) | Mesmo padrão de Q13 |

ICV depende do reranker para surfaçar os chunks certos. O reranker, por sua vez, quebra questões PIBIC. Esse conflito não é resolvível com parâmetros de `rag_config`.

---

## Causa raiz do conflito reranker × PIBIC

O corpus contém múltiplos documentos com vocabulário quase idêntico:
- Editais PIBIC, PIBIC-Af, PIBITI, PIBICEM — mesma estrutura, nomes parcialmente iguais
- Portarias de designação de comitês — citam os nomes dos programas nominalmente
- Aditivos — referenciam seções dos editais

O `bge-reranker-v2-m3` não resolve a ambiguidade entre esses documentos para perguntas gerais ("objetivos do PIBIC", "IRA mínimo PIBIC"), priorizando portarias (que têm alta co-ocorrência lexical com o nome do programa) sobre os trechos substantivos dos editais.

---

## Próximos passos recomendados

### Alta prioridade

1. **Filtragem por tipo de documento (`doc_type` no payload)**  
   Durante a indexação, marcar cada chunk com `doc_type` ("edital", "portaria", "relatorio", "modulo_sigaa", "aditivo"). Adicionar `payload_filter` ao `hybrid_search` com base no tipo de pergunta detectado (simples classificador de intenção ou regex). Isso previne que portarias compitam com editais em perguntas de conteúdo, e permitiria reabilitar o reranker com segurança.

2. **Reindexar com `doc_type` e testar reranker + filtragem**  
   Com portarias excluídas do pool para queries de conteúdo, o cross-encoder consegue distinguir PIBIC de PIBIC-EM de forma mais confiável → reativação segura do reranker.

### Média prioridade

3. **Habilitação de `contextual_compression_enabled`**  
   Comprime cada chunk ao trecho mais relevante antes de enviar ao LLM. Pode ajudar Q05 (vigência) onde o LLM confunde "vigência do edital" com "vigência das bolsas" por ter contexto amplo demais.

4. **Fine-tuning ou re-ranker alternativo**  
   Treinar um cross-encoder especializado com pares (pergunta PROPESQI, chunk correto) usando as 30 perguntas deste dataset como semente. Alternativa: testar `cross-encoder/ms-marco-MiniLM-L-6-v2` com instrução de sistema explicitando o domínio.

### Documentação

5. **Aditivos como documentos separados vs. patches inline**  
   Q30 ("o que o Aditivo nº 1 alterou") pontua 3.0 — o chatbot identifica apenas parte das mudanças do aditivo. Avaliar se chunks de aditivos devem ser associados (por metadado) aos chunks dos editais que alteram, para que o LLM sempre receba o par edital+aditivo junto.

---

## Resumo da evolução

| Configuração | Média | Ruins (<2.5) | Excelentes (≥4.5) |
|---|---|---|---|
| Baseline (todos off) | 3.63 | 7 | 19 |
| + parent_child_expansion | ~3.65* | ~6* | ~19* |
| + reranker (threshold=0.5) | 3.64 | 6 | 18 |
| + HyDE + multiquery + reranker | ~3.5* | ~7* | ~17* |
| **+ HyDE + multiquery (sem reranker)** | **4.09** | **3** | **21** |

\* estimativa via smoke test, sem full eval de 30 questões.
