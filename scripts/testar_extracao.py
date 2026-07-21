"""
Roda extração + identidade em TODOS os arquivos da fonte configurada.
Não usa a API da Anthropic — valida só leitura e chave estável.

    python -m scripts.testar_extracao
"""
from __future__ import annotations

import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.ingest.fontes import obter_fonte
from app.ingest.extractores import extrair_texto
from app.ingest.identidade import chave_estavel, extrair_periodo


def main() -> None:
    fonte = obter_fonte()
    arquivos = fonte.listar()
    print(f"{len(arquivos)} arquivo(s)\n")

    grupos: dict[str, list[str]] = {}

    for a in arquivos:
        chave = chave_estavel(a.nome)
        periodo = extrair_periodo(a.nome)
        grupos.setdefault(chave, []).append(a.nome)
        try:
            conteudo = fonte.baixar(a)
            texto = extrair_texto(a.nome, conteudo)
            n = len(texto)
            primeira = next((l.strip() for l in texto.splitlines() if l.strip()), "")
            ok = f"{n:>8} chars | 1ª linha: {primeira[:60]}"
        except Exception as e:
            ok = f"ERRO extração: {e.__class__.__name__}: {e}"
        print(f"[{chave:16}] periodo={str(periodo):9} | {a.nome[:42]:42} | {ok}")

    # mostra chaves com mais de um arquivo (fontes que se sobrescrevem entre si)
    print("\n=== chaves estáveis com múltiplos arquivos (mesma fonte) ===")
    for chave, nomes in sorted(grupos.items()):
        if len(nomes) > 1:
            print(f"  {chave}: {len(nomes)} arquivos -> {nomes}")
    print(f"\nTotal de fontes distintas (chaves): {len(grupos)}")


if __name__ == "__main__":
    main()
