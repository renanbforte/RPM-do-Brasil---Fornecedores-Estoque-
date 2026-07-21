"""
Configuração central do app.

Lê TODAS as credenciais e parâmetros do arquivo .env — nada fica hardcoded,
para que o mesmo código funcione em localhost e no servidor (EasyPanel).
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Raiz do projeto (…/ingestao-estoque) e carregamento do .env
_RAIZ = Path(__file__).resolve().parents[2]
load_dotenv(_RAIZ / ".env")


# ---- Banco de dados (SQLite — arquivo único) ------------------------------
# Caminho do arquivo .db. Se relativo, é resolvido a partir da raiz do projeto.
_db_raw = os.getenv("DB_PATH", "./data/estoque.db")
DB_PATH = str((_RAIZ / _db_raw).resolve()) if not os.path.isabs(_db_raw) else _db_raw

# ---- OpenAI (parser universal) --------------------------------------------
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

# ---- Pipeline -------------------------------------------------------------
PASTA_ENTRADA = os.getenv("PASTA_ENTRADA", "./data/entrada")

# ---- Fonte dos arquivos ---------------------------------------------------
# "local" = pasta PASTA_ENTRADA | "drive" = Google Drive (conta de serviço)
FONTE = os.getenv("FONTE", "local").strip().lower()
GDRIVE_FOLDER_ID = os.getenv("GDRIVE_FOLDER_ID", "")

# Caminho do JSON da conta de serviço; se relativo, resolve a partir da raiz
_cred_raw = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "")
GOOGLE_APPLICATION_CREDENTIALS = (
    str((_RAIZ / _cred_raw).resolve())
    if _cred_raw and not os.path.isabs(_cred_raw)
    else _cred_raw
)

# ---- API de consulta ------------------------------------------------------
# Token exigido no header Authorization: Bearer <token>
API_TOKEN = os.getenv("API_TOKEN", "")

# Caminho do banco para a API (aberto em somente-leitura). Usa DATABASE_PATH se
# definido; senão cai no mesmo DB_PATH da ingestão.
_dbapi_raw = os.getenv("DATABASE_PATH", "")
if _dbapi_raw:
    DATABASE_PATH = (
        str((_RAIZ / _dbapi_raw).resolve())
        if not os.path.isabs(_dbapi_raw) else _dbapi_raw
    )
else:
    DATABASE_PATH = DB_PATH
