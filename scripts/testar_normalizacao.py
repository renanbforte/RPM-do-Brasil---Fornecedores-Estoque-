"""
Testa o parser LLM (OpenAI) num arquivo pequeno real.
Requer OPENAI_API_KEY no .env.

    python -m scripts.testar_normalizacao "Cópia de LINK BELT - 05 2026.TXT"
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
from app.ingest.identidade import chave_estavel
from app.ingest.normalizador import normalizar_texto


def main() -> None:
    alvo = sys.argv[1] if len(sys.argv) > 1 else "Cópia de LINK BELT - 05 2026.TXT"

    fonte = obter_fonte()
    ref = next((a for a in fonte.listar() if a.nome == alvo), None)
    if not ref:
        print(f"Arquivo não encontrado na fonte: {alvo!r}")
        return

    texto = extrair_texto(ref.nome, fonte.baixar(ref))
    marca_hint = chave_estavel(ref.nome).upper()

    print(f"Arquivo : {ref.nome}")
    print(f"Chars    : {len(texto)} | marca_hint: {marca_hint}")
    print(f"Modelo   : (ver .env OPENAI_MODEL)\n")

    resultado = normalizar_texto(texto, ref.nome, marca_hint=marca_hint)

    print(f"empresa_fonte : {resultado.empresa_fonte}")
    print(f"cnpj          : {resultado.cnpj}")
    print(f"data_ref      : {resultado.data_referencia}")
    print(f"itens         : {len(resultado.itens)}\n")
    print("Primeiros 12 itens:")
    for it in resultado.itens[:12]:
        print(f"  cod={it.codigo!s:10} marca={it.marca!s:8} qtd={it.quantidade!s:6} "
              f"un={it.unidade!s:4} | {it.material}")


if __name__ == "__main__":
    main()
