"""
Normalização de texto — usada de forma CONSISTENTE em todo o sistema:
- nomes de materiais (campo material_normalizado)
- nomes de fornecedores (aliases e slug)

A mesma função é aplicada na gravação e na busca, para que a comparação
sempre bata (independente de acento, caixa ou pontuação).
"""
from __future__ import annotations

import re
import unicodedata


def remover_acentos(texto: str) -> str:
    """Remove acentos usando decomposição Unicode (ç -> c, á -> a)."""
    nfkd = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def normalizar(texto: str | None) -> str:
    """
    Normaliza para busca/comparação:
    - remove acentos
    - passa para minúsculas
    - troca qualquer pontuação/símbolo por espaço
    - colapsa espaços múltiplos e apara as pontas

    Ex.: "Cimento CP-II 50kg"      -> "cimento cp ii 50kg"
         "CIMENTO CPII SC 50KG"    -> "cimento cpii sc 50kg"
    """
    if not texto:
        return ""
    t = remover_acentos(str(texto))
    t = t.lower()
    # tudo que não for letra/número vira espaço
    t = re.sub(r"[^a-z0-9]+", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def slug_fornecedor(nome: str | None) -> str:
    """
    Gera o slug estável do fornecedor: normaliza e junta com hífen.
    Ex.: "Acme Materiais Ltda" -> "acme-materiais-ltda"
    """
    return normalizar(nome).replace(" ", "-")
