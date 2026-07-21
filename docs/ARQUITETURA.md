# Arquitetura do Backend de Estoque de Fornecedores

> Documento de referência para quem for construir o **agente no Dify**.
> Descreve **como os dados são armazenados**, **quais ferramentas são usadas**
> (local e no servidor) e **como o agente vai acessar** as informações.
> O agente **não** acessa o banco diretamente — ele consome uma **API HTTP**.

---

## 1. Para que serve

Fornecedores de **rolamentos** enviam listas de estoque (arquivos de formatos e
estruturas variadas) para uma pasta no Google Drive. O sistema lê esses arquivos,
normaliza o conteúdo com um LLM e grava tudo num banco. Uma **API** expõe consultas
como "quais fornecedores têm o material X?", "quanto o fornecedor Y tem?", etc.,
para serem respondidas por um **agente de IA no Dify**.

---

## 2. Visão geral do fluxo

```
Google Drive (pasta FORNECEDORES)
        │   (conta de serviço, somente leitura)
        ▼
   PIPELINE DE INGESTÃO (Python)
     1. lista os arquivos da pasta
     2. identifica a "fonte" (fornecedor) pelo nome do arquivo
     3. extrai o texto bruto (xlsx, csv, txt, docx)
     4. normaliza com OpenAI  → JSON estruturado por item
     5. grava de forma ATÔMICA no banco
     6. registra log da ingestão
        │
        ▼
   BANCO DE DADOS (SQLite — arquivo único)
        │
        ▼
   API HTTP (FastAPI)   ← é AQUI que o agente do Dify se conecta
        │
        ▼
   Agente no Dify
```

**Ponto-chave para o agente:** os dados vivem num arquivo **SQLite**, que **não**
é acessível pela rede. O agente do Dify fala com a **API HTTP (FastAPI)**, e a API
lê o SQLite. O agente nunca conecta no banco diretamente.

---

## 3. Como os dados são armazenados

### 3.1. Tecnologia de armazenamento
- **SQLite** — um único arquivo `.db` (ex: `data/estoque.db`).
- Sem servidor de banco. Backup = copiar o arquivo.
- Conexões usam **WAL** (leituras da API não travam a escrita da ingestão) e
  **chaves estrangeiras ativadas**.
- No servidor, o arquivo fica num **volume persistente**.

### 3.2. Tabelas

**`fornecedores`** — cada "fonte" de estoque (1 por identidade de arquivo)
| campo | descrição |
|---|---|
| `id` | PK |
| `nome_canonico` | rótulo de exibição (ex: "NTN STOCK LIST") |
| `slug` | **chave estável / identidade** (nome do arquivo sem ruído e sem data) |
| `empresa_fonte` | razão social encontrada no conteúdo (ex: "RODOMAQ ROLAMENTOS LTDA"), pode ser null |
| `cnpj` | CNPJ, se aparecer no conteúdo |
| `ativo`, `criado_em`, `atualizado_em` | controle |

**`estoque`** — os itens (substituídos por completo a cada atualização da fonte)
| campo | descrição |
|---|---|
| `id` | PK |
| `fornecedor_id` | FK → fornecedores |
| `codigo_fornecedor` | código do item na fonte (ex: 016431, E001567) |
| `material_original` | descrição/part-number exatamente como veio |
| `material_normalizado` | versão para busca (minúsculo, sem acento, sem pontuação) |
| `marca` | marca do rolamento (SKF, FAG, NTN, TIMKEN...) — atributo do item |
| `marca_normalizada` | marca para busca |
| `quantidade` | estoque disponível (número) |
| `unidade` | unidade (normalmente "pç" para rolamentos) |
| `data_referencia` | data de emissão/posição do estoque (do conteúdo do arquivo) |
| `arquivo_origem` | nome do arquivo de origem |
| `atualizado_em` | quando foi gravado |

**`ingestoes`** — log/auditoria de cada arquivo processado
| campo | descrição |
|---|---|
| `id`, `fornecedor_id` | |
| `arquivo`, `drive_file_id` | identificação do arquivo |
| `hash_arquivo` | SHA-256 do conteúdo (detecta se mudou) |
| `periodo` | data/período detectado |
| `status` | 'sucesso' \| 'erro' \| 'ignorado' |
| `erro`, `qtd_registros` | |
| `iniciado_em`, `finalizado_em` | |

**`fornecedor_aliases`** — histórico de variações de nome que apontam para a mesma fonte.

### 3.3. Modelo de identidade (importante para o agente entender)
- Uma **fonte/fornecedor** é identificada pela **chave estável do nome do arquivo**:
  removem-se "Cópia de", a extensão e a **data/período**. Ex.:
  - `Cópia de NTN - 05 2026.TXT` → chave **`ntn`**
  - `Cópia de NTN STOCK LIST JUN 9.xlsx` → chave **`ntn stock list`** (fonte diferente!)
- **Marca ≠ fornecedor.** A marca (SKF, FAG...) é um **atributo do item**. Um mesmo
  fornecedor (ex: RODOMAQ) manda vários arquivos, um por marca; e a mesma marca pode
  vir de fontes diferentes. Por isso o agente deve tratar **fornecedor** e **marca**
  como coisas distintas.

### 3.4. Regras de atualização (como o banco se mantém correto)
- **A pasta do Drive é a fonte da verdade.**
- **Substituição atômica:** ao processar um arquivo novo de uma fonte, todo o estoque
  antigo daquela fonte é apagado e o novo inserido **dentro de uma transação**. Se
  falhar, faz rollback e o estoque antigo permanece intacto. Nunca há mistura.
- **Detecção de mudança:** compara o **hash** do conteúdo; se for idêntico ao já
  processado, ignora (não reprocessa).
- **Reconciliação:** fonte que sumiu da pasta tem o estoque removido.

---

## 4. Ferramentas e tecnologias usadas

### 4.1. Linguagem e runtime
- **Python 3.11+**.
- **Configuração 100% via variáveis de ambiente (`.env`)** — nada de credencial ou
  caminho fixo no código (facilita rodar local e no servidor).

### 4.2. Banco de dados
- **SQLite** via módulo padrão `sqlite3` (sem dependência externa).

### 4.3. Leitura da fonte (Google Drive)
- **Google Drive API** via **conta de serviço** (`google-api-python-client` + `google-auth`),
  escopo **somente leitura**.
- A pasta do Drive é **compartilhada com o e-mail da conta de serviço**.
- Arquivos são baixados **em memória** durante o processamento (não são salvos como cópia).
- Suporta também uma **pasta local** como fonte alternativa (para testes).

### 4.4. Extração de conteúdo (por tipo de arquivo)
| Formato | Biblioteca |
|---|---|
| `.xlsx` | `openpyxl` |
| `.xls` | `xlrd` |
| `.csv` / `.txt` | `csv` (stdlib) + `chardet` (detecção de encoding) |
| `.docx` | `python-docx` |

### 4.5. Normalização (o "parser universal")
- **OpenAI** (SDK `openai`), modelo padrão **`gpt-4o-mini`** (configurável via env).
- Usa **Structured Outputs** (JSON garantido por schema).
- **Fatiamento** automático de arquivos grandes (mantendo o contexto das colunas).
- Recebe o texto bruto e devolve, por item: `codigo`, `material`, `marca`,
  `quantidade`, `unidade` — mais `empresa_fonte`, `cnpj`, `data_referencia` do cabeçalho.

### 4.6. Identidade de fornecedor
- Correspondência exata por chave estável + histórico de aliases; `rapidfuzz` para
  tolerar pequenos erros de digitação no nome.

### 4.7. API (camada que o Dify consome)
- **FastAPI** + **uvicorn**. Gera **schema OpenAPI** automaticamente (o Dify importa direto).

### 4.8. Servidor / deploy
- Deploy previsto no **EasyPanel**.
- Variáveis de ambiente configuradas lá (chave OpenAI, caminho do banco, pasta do Drive,
  credencial da conta de serviço).
- Arquivo SQLite e o JSON da conta de serviço em **volume persistente**.

---

## 5. Como o agente do Dify vai acessar (contrato da API)

> A API ainda está sendo finalizada, mas o **contrato** abaixo é o que o agente deve
> assumir. Todos os endpoints retornam **JSON**. Autenticação por header
> `Authorization: Bearer <token>`.

### `GET /estoque`
Busca itens por material/marca (busca tolerante, parcial, sem acento).
- Parâmetros: `material` (texto), `marca` (opcional), `limite` (opcional).
- Retorna lista de:
```json
{
  "fornecedor": "ntn stock list",
  "empresa_fonte": "…",
  "codigo": "10011490M",
  "material": "1205SK",
  "marca": "NTN",
  "quantidade": 180,
  "unidade": "pç",
  "data_referencia": "…"
}
```
Responde: "quais fornecedores têm o material X e quanto cada um tem".

### `GET /fornecedores`
Lista as fontes/fornecedores com contagem de itens e data da última atualização.

### `GET /fornecedores/{slug}/estoque`
Estoque de um fornecedor específico (opcionalmente filtrado por `material`).
Responde: "o fornecedor Y tem o material X? quanto?".

### `GET /status`
Última ingestão de cada fornecedor (status, quantidade, data).

**Observações para o agente:**
- A busca por material é **parcial e tolerante** — pode mandar "6205", "cimento", etc.
- Comparação de "quem tem mais" deve considerar a **mesma unidade** (rolamentos são
  quase sempre em peças).
- **Fornecedor** (a fonte) e **marca** são campos diferentes — o agente pode filtrar
  por qualquer um dos dois.

---

## 6. Estado atual (o que já funciona e o que falta)

| Componente | Estado |
|---|---|
| Leitura do Google Drive (conta de serviço) | ✅ funcionando |
| Extração (xlsx/xls/csv/txt/docx) | ✅ funcionando |
| Normalização via OpenAI | ✅ funcionando |
| Gravação atômica + reconciliação + detecção de mudança | ✅ funcionando |
| Banco populado (dados reais) | ✅ ~24 fornecedores, ~39 mil itens |
| **API FastAPI (que o Dify consome)** | ⏳ **a construir** |
| Deploy no EasyPanel | ⏳ pendente |

Resumo: a **ingestão e o banco** estão prontos e funcionando; falta publicar a **API**
para o agente do Dify consumir.
