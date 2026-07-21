"""
Executa a sincronização da pasta -> banco.

Uso:
    python -m scripts.sincronizar                 # processa a pasta inteira + reconcilia
    python -m scripts.sincronizar --limite 2      # só as 2 primeiras fontes (teste)
    python -m scripts.sincronizar --apenas "link belt,ntn"   # só essas chaves
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.ingest.pipeline import sincronizar


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limite", type=int, default=None)
    ap.add_argument("--apenas", type=str, default=None,
                    help="chaves separadas por vírgula")
    ap.add_argument("--forcar", action="store_true",
                    help="reprocessa mesmo se o hash já foi visto")
    args = ap.parse_args()

    apenas = {c.strip() for c in args.apenas.split(",")} if args.apenas else None

    print("Sincronizando...\n")
    r = sincronizar(limite=args.limite, apenas=apenas, forcar=args.forcar)

    print("\n===== RESUMO =====")
    print(f"  processados     : {r.processados}")
    print(f"  ignorados       : {r.ignorados}")
    print(f"  erros           : {r.erros}")
    print(f"  itens inseridos : {r.itens_inseridos}")
    if r.reconciliados:
        print(f"  reconciliados   : {r.reconciliados}")


if __name__ == "__main__":
    main()
