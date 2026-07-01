# Deploy na AWS (Gemini para LLM + embeddings)

Guia para rodar o PROPESQI RAG Chatbot em uma única instância EC2 via Docker
Compose, usando o Gemini como único provedor de LLM/embeddings — sem Ollama,
sem GPU. O reranker (`BAAI/bge-reranker-v2-m3`) e o encoder esparso BM42
continuam rodando localmente, mas em CPU (ver `backend/Dockerfile.cloud`).

Arquitetura: mesma do `docker-compose.yml` original (Postgres + Qdrant +
backend + frontend em uma rede Docker interna), só que sem o serviço
`ollama` e sem reserva de GPU — ver `docker-compose.aws.yml` na raiz do repo.
Optou-se por uma única instância EC2 em vez de ECS/Fargate por ser mais
simples e barato para o volume de uso institucional; pode ser migrado depois
se o tráfego crescer.

## 1. Instância EC2

- Tipo recomendado: `t3.xlarge` (4 vCPU / 16 GiB) — cobre Postgres + Qdrant +
  backend (reranker + BM42 em CPU) + frontend confortavelmente.
  Mínimo viável: `t3.large` (2 vCPU / 8 GiB), mais justo sob carga.
- AMI: Amazon Linux 2023 ou Ubuntu 22.04/24.04 (o `user-data.sh` cobre ambos).
- Volume EBS: gp3, dimensionado pelo tamanho esperado do acervo de documentos
  (uploads + índice Qdrant + Postgres). 50–100 GiB é um ponto de partida
  razoável para um acervo institucional de editais/resoluções.
- User data: cole o conteúdo de `deploy/aws/user-data.sh` no campo "User data"
  ao lançar a instância. Ele instala Docker + o plugin Compose, mas **não**
  sobe o stack sozinho (precisa do `.env` com segredos primeiro).

## 2. Security Group

- Porta 443 (HTTPS) e 80 (HTTP, redireciona para 443) — abertas ao público.
- Porta 22 (SSH) — restrita ao(s) IP(s) do(s) administrador(es), nunca `0.0.0.0/0`.
- Nenhuma outra porta precisa ser exposta: Postgres, Qdrant e o backend (8000)
  ficam só na rede interna do Docker Compose.

## 3. Preparar o `.env`

Copie `.env.aws.example` da raiz do repo, preencha os valores `CHANGE_ME_*` e
gere os segredos localmente (não na instância, para não deixar rastro em
histórico de shell da AWS):

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"       # SECRET_KEY
python3 -c "import secrets; print(secrets.token_urlsafe(32))"   # QDRANT_API_KEY
```

`GOOGLE_API_KEY` é obrigatório neste modo (LLM e embeddings via Gemini).
Gere uma chave em https://aistudio.google.com/apikey.

`LLMWHISPERER_API_KEY` também é obrigatório se houver PDFs escaneados a
processar — o OCR roda inteiramente na API do LLMWhisperer, sem Tesseract/
OpenCV locais. Gere uma chave em https://unstract.com/llmwhisperer/.

Transfira o repositório e o `.env` preenchido para a instância (nunca versione
o `.env`):

```bash
scp -r . ec2-user@<IP_DA_INSTANCIA>:/opt/propesqi
scp .env ec2-user@<IP_DA_INSTANCIA>:/opt/propesqi/.env
```

## 4. Subir o stack

Na instância:

```bash
cd /opt/propesqi
docker compose -f docker-compose.aws.yml up -d
docker compose -f docker-compose.aws.yml ps       # confere que tudo ficou healthy
curl -f http://localhost:8000/health              # deve responder {"status":"ok"}
```

Um banco novo já é criado com `rag_config.llm_provider = 'gemini'` e
`embedding_provider = 'gemini'` (ver `init/01_schema.sql`) — nenhum passo
extra é necessário para um primeiro deploy do zero.

## 5. TLS (HTTPS)

Recomendado: Certbot direto no nginx do container `frontend`, ou um volume
adicional montando os certificados do host. Alternativa mais gerenciada:
colocar a instância atrás de um Application Load Balancer com certificado ACM
— mais robusto, mas adiciona um componente extra à arquitetura atual.

## 6. Se estiver migrando um banco já existente (documentos indexados com bge-m3)

Embeddings de providers diferentes não são intercambiáveis mesmo com a mesma
dimensão (1024). Depois de trocar `embedding_provider`/`embedding_model` para
`gemini`/`gemini-embedding-001` (via painel admin ou `UPDATE rag_config ...`),
reindexe tudo:

```
POST /api/documents/reindex-all
Body: {"scope": "all"}
```

(endpoint existente, `backend/app/api/routes/documents.py`) — purga os vetores
do Qdrant e reprocessa todos os documentos com o novo provider. Acompanhe o
progresso pelo painel admin ou pelo WebSocket `/ws`.

## O que NÃO está incluído aqui

Provisionamento automatizado (Terraform/CloudFormation) e execução de
comandos `aws` CLI ficam por conta de quem está de posse da conta AWS —
scripts aqui são um guia manual, não uma automação que roda sozinha.
