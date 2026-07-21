"""
Camada de conexão com o SQLite (biblioteca padrão `sqlite3`).

Aplica os PRAGMAs importantes em toda conexão:
- foreign_keys=ON  → respeita as FKs (SQLite vem com isso desligado por padrão)
- journal_mode=WAL → leituras (agente/API) não bloqueiam a escrita (ingestão)
- busy_timeout     → espera um pouco em vez de estourar erro se o arquivo estiver ocupado
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from app.core import config


@contextmanager
def conectar() -> Iterator[sqlite3.Connection]:
    """
    Abre uma conexão com o arquivo SQLite (criando a pasta se necessário).

    Uso:
        with conectar() as con:
            cur = con.execute("SELECT ...")
            con.commit()
    """
    Path(config.DB_PATH).parent.mkdir(parents=True, exist_ok=True)

    con = sqlite3.connect(config.DB_PATH, timeout=10)
    con.row_factory = sqlite3.Row          # acesso por nome de coluna: row["nome"]
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("PRAGMA journal_mode = WAL")
    con.execute("PRAGMA busy_timeout = 5000")
    try:
        yield con
    finally:
        con.close()
