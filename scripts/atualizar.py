"""
Comando ÚNICO de atualização: roda a ingestão (Drive -> banco local) e, se
tudo der certo, publica o banco pronto no servidor.

    python -m scripts.atualizar

É este o comando que você roda (ou agenda) para atualizar o servidor.
A ingestão pesada acontece aqui (onde há RAM); o servidor só recebe o .db.
"""
from __future__ import annotations

import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.ingest.pipeline import sincronizar
from scripts.publicar import publicar


def main() -> None:
    print("1/2 — Ingerindo do Drive para o banco local...\n")
    r = sincronizar()
    print(f"\n  processados={r.processados} ignorados={r.ignorados} "
          f"erros={r.erros} itens={r.itens_inseridos}")

    print("\n2/2 — Publicando o banco no servidor...")
    resp = publicar()
    print("  OK:", resp)
    print("\nServidor atualizado. ✅")


if __name__ == "__main__":
    main()
