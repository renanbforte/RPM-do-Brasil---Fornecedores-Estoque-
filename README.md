# Ingestão de Estoque de Fornecedores

Sistema que lê arquivos de estoque enviados por fornecedores (em formatos e
estruturas variadas), normaliza o conteúdo usando um **LLM (OpenAI) como parser
universal** e grava tudo num **SQLite** (arquivo único) — servindo depois uma
API de consulta para um agente no Dify.

> **Status atual:** Fase 1 — fundação do banco de dados **concluída**.
> Pipeline de ingestão e API de consulta em construção.

---

## Como funciona (visão geral)

```
pasta local (simula o Drive)
      │
      ▼
[1] varre a pasta            → a pasta é a FONTE DA VERDADE
[2] identifica o fornecedor  → nome do arquivo + conteúdo, com fuzzy match e histórico
[3] extrai o bruto           → .xlsx / .csv / .txt / .docx
[4] normaliza via OpenAI     → JSON [{codigo, material, marca, quantidade, unidade}]
[5] valida                   → quantidade numérica, campos obrigatórios
[6] grava ATÔMICO            → BEGIN → DELETE do fornecedor → INSERT → COMMIT/ROLLBACK
[7] loga em `ingestoes`
      │
      ▼
[8] API FastAPI              → consumida pelo Dify
```

### Regras de negócio importantes
- **Substituição atômica:** ao processar arquivos novos de um fornecedor, todo o
  estoque antigo dele é apagado e o novo inserido dentro de **uma transação**. Se
  algo falhar, dá `ROLLBACK` e o estoque antigo permanece intacto — nunca há mistura.
- **Pasta = fonte da verdade:** o que não está mais na pasta é considerado
  removido/vencido; o estoque correspondente é zerado na sincronização (o cadastro
  do fornecedor permanece no histórico).
- **Identidade tolerante:** o mesmo fornecedor pode aparecer como `ACME`, `acme`,
  `acme_estoque` ou com uma letra faltando. A normalização + fuzzy match (pg_trgm)
  + tabela de aliases resolvem isso e mantêm um histórico de nomes já vistos.

---

## Schema do banco (SQLite)

Tudo vive num único arquivo `.db` (ver `DB_PATH` no `.env`). Conexões usam WAL
(leituras da API não bloqueiam a escrita da ingestão) e `foreign_keys=ON`.

| Tabela | Papel |
|---|---|
| `fornecedores` | cadastro canônico (nome + `slug` único + ativo) |
| `fornecedor_aliases` | toda variação de nome já vista → aponta pro fornecedor |
| `estoque` | itens de estoque (original + normalizado, quantidade, unidade, arquivo) |
| `ingestoes` | log/auditoria de cada arquivo processado |

A busca por material usa o campo normalizado (`LIKE '%cimento%'`). O fuzzy match
de fornecedores (nome com typo/caixa alta) é feito em Python com **`rapidfuzz`**.
Se o volume crescer, dá para ativar **FTS5** (busca textual nativa do SQLite).

---

## Setup

### Pré-requisitos
- Python 3.11+
- Nada de servidor de banco: o SQLite é criado automaticamente no caminho `DB_PATH`

### Passos
```bash
# 1. criar/ativar um venv (opcional, recomendado)
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate    # Linux/Mac

# 2. instalar dependências
pip install -r requirements.txt

# 3. configurar o ambiente
copy .env.example .env         # Windows  (cp no Linux/Mac)
# edite o .env: OPENAI_API_KEY, API_TOKEN, e (para ingestão) as vars do Drive

# 4. aplicar o schema no banco (idempotente — pode rodar de novo sem problema)
python -m scripts.apply_schema

# 5. rodar a ingestão (Drive -> banco)
python -m scripts.sincronizar
```

Toda a configuração vem do `.env` — **nada é hardcoded**. No deploy (EasyPanel),
basta apontar `DATABASE_PATH` para um arquivo num **volume persistente** e informar
as variáveis de ambiente.

---

## API de consulta (rodar e testar)

A API é consumida pelo agente do Dify. Sobe com uvicorn:

```bash
uvicorn app.api.main:app --host 0.0.0.0 --port 8000
```

Precisa de duas variáveis no `.env`:
- `API_TOKEN` — token exigido no header `Authorization: Bearer <token>`
- `DATABASE_PATH` — caminho do `.db` (vazio = usa o `DB_PATH`). A API abre em **somente-leitura**.

Documentação interativa (Swagger) e schema OpenAPI (para importar no Dify):
- `http://localhost:8000/docs`
- `http://localhost:8000/openapi.json`

### Testando com curl

```bash
TOKEN=dev-token-local-123   # o mesmo do seu .env

# health (público, sem token)
curl http://localhost:8000/health

# sem token -> 401
curl -i http://localhost:8000/estoque?material=6205

# quais fornecedores têm "6205" (com token)
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/estoque?material=6205&limite=5"

# filtrando por marca
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/estoque?material=6205&marca=fag"

# lista de fornecedores (contagem + última atualização)
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/fornecedores

# estoque de um fornecedor específico
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/fornecedores/skf/estoque?material=6205"

# status da última ingestão de cada fornecedor
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/status
```

---

## Deploy no EasyPanel

A imagem (`Dockerfile`) sobe a **API** na porta **8000**, com o banco num **volume
persistente** montado em `/data`.

**Passo a passo:**

1. **Suba o código** para um repositório Git (ou use o build por upload do EasyPanel).
2. No EasyPanel, crie um **App** do tipo **Dockerfile** apontando para este projeto.
3. **Volume persistente:** monte um volume no container em **`/data`**
   (é onde fica `estoque.db`, definido por `DATABASE_PATH=/data/estoque.db`).
4. **Porta:** exponha a **8000**. O EasyPanel cria o domínio/HTTPS.
5. **Health check:** aponte para **`GET /health`** (público, sem token).
6. **Variáveis de ambiente** (aba *Environment*):
   - `API_TOKEN` — um token forte (o Dify vai enviar no header)
   - `DATABASE_PATH=/data/estoque.db`
   - **Para rodar a ingestão** no servidor (opcional, se o pipeline rodar aqui):
     `OPENAI_API_KEY`, `OPENAI_MODEL`, `FONTE=drive`, `GDRIVE_FOLDER_ID`,
     `GOOGLE_APPLICATION_CREDENTIALS` (caminho do JSON da conta de serviço no volume).
7. **Conta de serviço do Drive:** suba o `service_account.json` para o volume
   (ex: `/data/service_account.json`) e aponte `GOOGLE_APPLICATION_CREDENTIALS` para ele.
   **Não** coloque esse arquivo na imagem.
8. **Popular o banco:** rode a ingestão uma vez (via *Console/Terminal* do EasyPanel):
   `python -m scripts.sincronizar`. Para atualizações periódicas, agende esse comando
   (cron do EasyPanel) na frequência desejada.

> A imagem **não** contém `.env`, `credentials/` nem `data/` (ver `.dockerignore`) —
> tudo entra por variável de ambiente e volume, nunca embutido.

---

## Estrutura do projeto

```
ingestao-estoque/
├─ app/
│  ├─ core/
│  │  ├─ config.py         # lê o .env (banco, OpenAI, Drive, API_TOKEN)
│  │  └─ normalizacao.py   # normalização consistente de texto (material/fornecedor)
│  ├─ db/
│  │  ├─ connection.py     # conexão sqlite3 (WAL + foreign_keys) p/ ingestão
│  │  └─ repositorio.py    # identidade, gravação atômica, log, reconciliação
│  ├─ ingest/
│  │  ├─ fontes.py         # FonteLocal / FonteGoogleDrive
│  │  ├─ extractores.py    # extrai texto bruto (xlsx/xls/csv/txt/docx)
│  │  ├─ identidade.py     # chave estável + período a partir do nome
│  │  ├─ normalizador.py   # parser universal via OpenAI (Structured Outputs)
│  │  └─ pipeline.py       # orquestra a sincronização
│  └─ api/
│     └─ main.py           # API FastAPI (consumida pelo Dify)
├─ db/
│  └─ schema.sql           # DDL das tabelas (SQLite)
├─ scripts/
│  ├─ apply_schema.py      # cria/atualiza o schema (idempotente)
│  ├─ sincronizar.py       # roda a ingestão (Drive/local -> banco)
│  └─ testar_*.py          # testes de fonte/extração/normalização
├─ credentials/            # JSON da conta de serviço (fora do git)
├─ data/
│  ├─ estoque.db           # o banco (gerado; fora do git)
│  └─ entrada/             # pasta local que simula o Google Drive
├─ docs/ARQUITETURA.md     # explicação do sistema (para o time do Dify)
├─ Dockerfile              # imagem p/ EasyPanel (API na porta 8000)
├─ .dockerignore
├─ .env.example
├─ requirements.txt
└─ README.md
```

---

## Próximos passos (roadmap)

- ✅ **[Fase 1]** Pipeline de ingestão: extractors por tipo, parser LLM (OpenAI),
  matching de fornecedor, gravação atômica + reconciliação da pasta.
- ✅ **[Fase 1]** Leitura direto do Google Drive (conta de serviço).
- ✅ **[Fase 1]** API FastAPI de consulta (`/estoque`, `/fornecedores`,
  `/fornecedores/{slug}/estoque`, `/status`, `/health`).
- ⏳ **[Deploy]** Publicar a API no EasyPanel e conectar o agente do Dify.
- ⏳ **[Refino]** Corrigir truncamento de arquivos densos (HMS) e limpeza de
  `empresa_fonte` nos arquivos sem razão social.
