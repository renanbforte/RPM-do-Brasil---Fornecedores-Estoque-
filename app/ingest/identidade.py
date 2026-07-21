"""
Identidade da fonte a partir do NOME do arquivo.

Regra (definida com os arquivos reais):
- A CHAVE ESTÁVEL é o nome sem ruído ("Cópia de", extensão) e SEM a data/período.
- Dois nomes que diferem em algo além da data são fontes DIFERENTES.
  Ex: "NTN - 05 2026.TXT"        -> chave "ntn"
      "NTN STOCK LIST JUN 9.xlsx" -> chave "ntn stock list"  (fonte diferente)
- A data/período é extraída à parte e usada para recência.
"""
from __future__ import annotations

import re
from pathlib import Path

from app.core.normalizacao import normalizar

_EXTENSOES = {".txt", ".xlsx", ".xls", ".csv", ".docx"}

# ruídos de cópia que aparecem no começo/meio do nome
_RUIDOS = ["copia de", "copy of", "nova"]

# meses (pt e en, abreviados) para remover tokens de data tipo "jun 9"
_MESES = (
    "jan|fev|mar|abr|mai|jun|jul|ago|set|out|nov|dez|"
    "feb|apr|may|aug|sep|oct|dec"
)


def _tirar_extensoes(nome: str) -> str:
    """Remove extensões conhecidas, inclusive repetidas (ex: .TXT.TXT)."""
    p = Path(nome)
    while p.suffix.lower() in _EXTENSOES:
        p = p.with_suffix("")
    return p.name


def extrair_periodo(nome: str) -> str | None:
    """Melhor-esforço: devolve o primeiro token de data encontrado no nome."""
    n = normalizar(nome)
    padroes = [
        r"\d{4} \d{2} \d{2}",                  # 2026-02-10 (após normalizar vira espaço)
        r"\b\d{1,2} \d{1,2} \d{2,4}\b",        # 01 04 2025
        r"\b\d{2} \d{4}\b",                     # 05 2026
        rf"\b(?:{_MESES}) \d{{1,2}}\b",         # jun 9
        r"\b\d{8}\b",                           # 20260706
    ]
    for pat in padroes:
        m = re.search(pat, n)
        if m:
            return m.group(0).strip()
    return None


def _remover_datas(t: str) -> str:
    t = re.sub(r"\d{4} \d{2} \d{2}", " ", t)          # 2026 02 10
    t = re.sub(r"\b\d{1,2} \d{1,2} \d{2,4}\b", " ", t)  # 01 04 2025
    t = re.sub(r"\b\d{2} \d{4}\b", " ", t)             # 05 2026
    t = re.sub(rf"\b(?:{_MESES})(?: \d{{1,2}})?\b", " ", t)  # jun 9 / jun
    t = re.sub(r"\b\d{6,8}\b", " ", t)                 # 20260706 / 161641
    t = re.sub(r"\b(?:19|20)\d{2}\b", " ", t)          # ano solto 2026
    return t


def chave_estavel(nome: str) -> str:
    """
    Gera a chave estável (identidade da fonte) a partir do nome do arquivo.
    """
    base = _tirar_extensoes(nome)
    t = normalizar(base)  # lower, sem acento, sem pontuação, espaços simples

    # remove ruídos de cópia (podem repetir: "copia de nova copia de ...")
    mudou = True
    while mudou:
        mudou = False
        for r in _RUIDOS:
            novo = re.sub(rf"\b{re.escape(r)}\b", " ", t)
            novo = re.sub(r"\s+", " ", novo).strip()
            if novo != t:
                t, mudou = novo, True

    t = _remover_datas(t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def rotulo_exibicao(nome: str) -> str:
    """Rótulo amigável para exibição (a partir da chave estável)."""
    return chave_estavel(nome).upper()
