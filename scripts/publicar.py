"""
Publica o banco local (data/estoque.db) no servidor, via o endpoint /admin/db.

Usa API_BASE_URL e API_TOKEN do .env.

    python -m scripts.publicar
"""
from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core import config


def publicar() -> dict:
    """Envia o .db local para {API_BASE_URL}/admin/db. Retorna a resposta."""
    if not config.API_BASE_URL:
        raise RuntimeError("API_BASE_URL não configurada no .env")
    if not config.API_TOKEN:
        raise RuntimeError("API_TOKEN não configurada no .env")

    db = Path(config.DB_PATH)
    if not db.exists():
        raise RuntimeError(f"Banco local não encontrado: {db}")

    dados = db.read_bytes()
    url = config.API_BASE_URL + "/admin/db"
    req = urllib.request.Request(
        url, data=dados, method="POST",
        headers={
            "Authorization": "Bearer " + config.API_TOKEN,
            "Content-Type": "application/octet-stream",
        },
    )
    import json
    with urllib.request.urlopen(req, timeout=180) as resp:
        return json.loads(resp.read().decode())


def main() -> None:
    print(f"Publicando {config.DB_PATH} em {config.API_BASE_URL}/admin/db ...")
    r = publicar()
    print("OK:", r)


if __name__ == "__main__":
    main()
