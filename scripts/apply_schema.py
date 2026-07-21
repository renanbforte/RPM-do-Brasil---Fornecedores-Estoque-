"""
Cria/atualiza o schema do app no arquivo SQLite (idempotente).

Rodar:
    python -m scripts.apply_schema
"""
from __future__ import annotations

import sys
from pathlib import Path

# saída UTF-8 mesmo em console Windows (cp1252)
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# permite `python -m scripts.apply_schema` e `python scripts/apply_schema.py`
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core import config
from app.db.connection import conectar

_RAIZ = Path(__file__).resolve().parents[1]
_SCHEMA_SQL = _RAIZ / "db" / "schema.sql"


def main() -> None:
    sql = _SCHEMA_SQL.read_text(encoding="utf-8")
    print(f"→ Banco SQLite: {config.DB_PATH}")

    with conectar() as con:
        con.executescript(sql)   # cria schema + tabelas + índices
        con.commit()

        # resumo do que ficou no arquivo
        tabelas = [
            r["name"]
            for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        ]
        indices = [
            r["name"]
            for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='index' "
                "AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        ]

    print("  ✓ schema aplicado")
    print("\nTabelas:")
    for t in tabelas:
        print(f"  • {t}")
    print("\nÍndices:")
    for i in indices:
        print(f"  • {i}")
    print("\nPronto. ✅")


if __name__ == "__main__":
    main()
