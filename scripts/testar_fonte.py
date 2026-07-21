"""
Testa a fonte de arquivos configurada no .env (local ou drive).
Lista o que encontrou e confirma que consegue baixar o primeiro arquivo.

Rodar:
    python -m scripts.testar_fonte
"""
from __future__ import annotations

import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core import config
from app.ingest.fontes import obter_fonte, hash_bytes


def main() -> None:
    print(f"FONTE = {config.FONTE}")
    if config.FONTE == "drive":
        print(f"  pasta Drive : {config.GDRIVE_FOLDER_ID}")
        print(f"  credencial  : {config.GOOGLE_APPLICATION_CREDENTIALS}")

    fonte = obter_fonte()
    arquivos = fonte.listar()
    print(f"\n{len(arquivos)} arquivo(s) encontrado(s):")
    for a in arquivos:
        tam = f"{a.tamanho} bytes" if a.tamanho else "?"
        print(f"  • {a.nome}  [{a.mime or a.extensao}]  {tam}")

    if arquivos:
        primeiro = arquivos[0]
        conteudo = fonte.baixar(primeiro)
        print(f"\nDownload OK do primeiro: {primeiro.nome}")
        print(f"  bytes: {len(conteudo)}  sha256: {hash_bytes(conteudo)[:16]}...")


if __name__ == "__main__":
    main()
