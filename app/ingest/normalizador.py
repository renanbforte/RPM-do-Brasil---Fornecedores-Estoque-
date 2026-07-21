"""
Parser universal via OpenAI.

Recebe o TEXTO BRUTO de um arquivo (de qualquer fornecedor/formato) e devolve
uma lista estruturada de itens de estoque, além de metadados detectados no
conteúdo (empresa/CNPJ/data de emissão).

Pontos de projeto exigidos pelos arquivos reais:
- Structured Outputs (response_format json_schema) → JSON sempre válido.
- Fatiamento de arquivos grandes (SKF ~784k chars) preservando o CABEÇALHO
  em cada lote, para o modelo saber as colunas.
- Cabeçalho é só contexto (empresa/colunas/período); itens são extraídos
  apenas da seção de DADOS — evita contar item duplicado entre lotes.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Iterator

from app.core import config

# --------------------------------------------------------------------------
# Estruturas de saída
# --------------------------------------------------------------------------
@dataclass
class ItemEstoque:
    codigo: str | None
    material: str
    marca: str | None
    quantidade: float | None
    unidade: str | None


@dataclass
class ResultadoNormalizacao:
    empresa_fonte: str | None = None
    cnpj: str | None = None
    data_referencia: str | None = None
    itens: list[ItemEstoque] = field(default_factory=list)


# --------------------------------------------------------------------------
# Schema do Structured Outputs (JSON garantido pela OpenAI)
# --------------------------------------------------------------------------
_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["empresa_fonte", "cnpj", "data_referencia", "itens"],
    "properties": {
        "empresa_fonte": {"type": ["string", "null"]},
        "cnpj": {"type": ["string", "null"]},
        "data_referencia": {"type": ["string", "null"]},
        "itens": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["codigo", "material", "marca", "quantidade", "unidade"],
                "properties": {
                    "codigo": {"type": ["string", "null"]},
                    "material": {"type": "string"},
                    "marca": {"type": ["string", "null"]},
                    "quantidade": {"type": ["number", "null"]},
                    "unidade": {"type": ["string", "null"]},
                },
            },
        },
    },
}

_SYSTEM = (
    "Você é um extrator de listas de estoque de fornecedores de ROLAMENTOS. "
    "Recebe texto bruto (de planilhas, TXT de ERP, etc.) e devolve os itens de "
    "estoque de forma estruturada. Regras:\n"
    "- Extraia UM item por produto listado na seção DADOS.\n"
    "- 'codigo' = código do item no fornecedor (se houver), senão null.\n"
    "- 'material' = descrição/part-number do produto (obrigatório).\n"
    "- 'marca' = a MARCA do rolamento, nesta ordem de prioridade:\n"
    "    1) uma coluna/valor de marca explícito nos DADOS (ex: coluna BRAND);\n"
    "    2) uma marca no início/dentro da descrição (ex: 'SKF 6205...' -> SKF);\n"
    "    3) a DICA DE MARCA do nome do arquivo, SOMENTE se for uma marca real de "
    "rolamento (ex: SKF, FAG, NTN, TIMKEN, NSK, KOYO, NACHI, INA, EATON...).\n"
    "  NUNCA use termos genéricos de nome de arquivo como 'STOCK LIST', "
    "'MASTER ITEM LIST', 'INVENTORY FILE', 'RAPOR', 'REPORT', 'LISTA' como marca. "
    "Se não houver marca real, use null.\n"
    "- 'quantidade' = estoque disponível como NÚMERO (use ponto decimal, sem "
    "separador de milhar). Se não houver, null.\n"
    "- 'unidade' = unidade se explícita (pç, un, kg...), senão null.\n"
    "- 'empresa_fonte' = razão social REAL da empresa no CABEÇALHO (ex: 'RODOMAQ "
    "ROLAMENTOS LTDA', 'BMI Bearings'). Se o cabeçalho não trouxer um nome de empresa "
    "real, use null — NUNCA invente a partir do nome do arquivo.\n"
    "- 'cnpj' = CNPJ se aparecer, senão null. 'data_referencia' = data de emissão/"
    "posição do estoque, senão null.\n"
    "- IGNORE cabeçalhos, títulos de coluna, totais, rodapés, endereços e número de "
    "página. NÃO invente itens."
)


def _lotes(texto: str, max_chars: int, linhas_contexto: int) -> Iterator[tuple[str | None, str]]:
    """
    Fatia o TEXTO INTEIRO em lotes de ~max_chars (nenhuma linha é descartada).
    - 1º lote: contexto=None (o modelo lê tudo, inclusive o cabeçalho, e ignora
      as linhas que não são itens).
    - lotes seguintes: contexto = primeiras `linhas_contexto` linhas, só para
      lembrar as COLUNAS (não são itens, então não há dupla contagem).
    """
    linhas = texto.splitlines()
    contexto = "\n".join(linhas[:linhas_contexto])

    atual: list[str] = []
    tam = 0
    primeiro = True
    for ln in linhas:
        if atual and tam + len(ln) > max_chars:
            yield (None if primeiro else contexto), "\n".join(atual)
            primeiro, atual, tam = False, [], 0
        atual.append(ln)
        tam += len(ln) + 1
    if atual:
        yield (None if primeiro else contexto), "\n".join(atual)


def _chamar_openai(client, contexto: str | None, corpo: str, nome_arquivo: str,
                   marca_hint: str | None) -> dict:
    """Uma chamada de extração para um lote."""
    partes = [
        f"NOME DO ARQUIVO: {nome_arquivo}",
        f"DICA DE MARCA (do nome do arquivo): {marca_hint or '(nenhuma)'}",
        "",
    ]
    if contexto:
        partes += [
            "=== CONTEXTO DE COLUNAS (apenas referência — NÃO extraia itens daqui) ===",
            contexto,
            "",
        ]
    partes += [
        "=== DADOS (extraia os itens de estoque destas linhas; ignore cabeçalhos, "
        "títulos de coluna, totais e rodapés; se aparecerem, pegue empresa/cnpj/data) ===",
        corpo,
    ]
    user = "\n".join(partes)
    resp = client.chat.completions.create(
        model=config.OPENAI_MODEL,
        temperature=0,
        messages=[
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": user},
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {"name": "estoque", "schema": _SCHEMA, "strict": True},
        },
    )
    escolha = resp.choices[0]
    # devolve o texto e o motivo de parada ("length" = saída truncada)
    return escolha.message.content, escolha.finish_reason


def normalizar_texto(
    texto: str,
    nome_arquivo: str,
    marca_hint: str | None = None,
    max_chars_por_lote: int = 8000,
    linhas_contexto: int = 15,
) -> ResultadoNormalizacao:
    """
    Normaliza o texto bruto de um arquivo em itens de estoque via OpenAI.
    Fatiamento automático para arquivos grandes.
    """
    if not config.OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY não configurada no .env")

    from openai import OpenAI

    client = OpenAI(api_key=config.OPENAI_API_KEY)
    resultado = ResultadoNormalizacao()

    # contexto de colunas para reusar quando um lote precisar ser subdividido
    contexto_padrao = "\n".join(texto.splitlines()[:linhas_contexto])

    # pilha de trabalho (contexto, corpo). Se um lote truncar a saída do modelo,
    # ele é dividido ao meio e as partes voltam para a pilha.
    pilha = list(_lotes(texto, max_chars_por_lote, linhas_contexto))
    pilha.reverse()

    while pilha:
        contexto, corpo = pilha.pop()
        conteudo, motivo = _chamar_openai(client, contexto, corpo, nome_arquivo, marca_hint)

        if motivo == "length":
            linhas = corpo.splitlines()
            if len(linhas) <= 1:
                raise ValueError("saída truncada mesmo com lote de 1 linha")
            meio = len(linhas) // 2
            ctx = contexto or contexto_padrao
            # reempilha as duas metades (a primeira será processada antes)
            pilha.append((ctx, "\n".join(linhas[meio:])))
            pilha.append((ctx, "\n".join(linhas[:meio])))
            continue

        data = json.loads(conteudo)

        # metadados: pega o primeiro valor não-nulo encontrado entre os lotes
        resultado.empresa_fonte = resultado.empresa_fonte or data.get("empresa_fonte")
        resultado.cnpj = resultado.cnpj or data.get("cnpj")
        resultado.data_referencia = resultado.data_referencia or data.get("data_referencia")

        for it in data.get("itens", []):
            if not it.get("material"):
                continue  # material é obrigatório; descarta lixo
            resultado.itens.append(ItemEstoque(
                codigo=it.get("codigo"),
                material=it["material"],
                marca=it.get("marca"),
                quantidade=it.get("quantidade"),
                unidade=it.get("unidade"),
            ))

    return resultado
