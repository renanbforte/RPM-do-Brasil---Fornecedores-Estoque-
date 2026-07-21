"""
Orquestrador da sincronização.

Fluxo (a pasta é a fonte da verdade):
  1. lista os arquivos da fonte (Drive/local) e agrupa por chave estável,
     escolhendo o MAIS RECENTE quando há nomes iguais (recência).
  2. para cada fonte:
        - hash igual ao já processado  -> ignora
        - senão: extrai -> normaliza (OpenAI) -> gravação ATÔMICA
        - erro de normalização         -> registra erro, estoque antigo intacto
  3. reconcilia: fontes que sumiram da pasta têm o estoque removido
     (só em execução completa, não em testes limitados).
"""
from __future__ import annotations

from dataclasses import dataclass

from app.db import repositorio as repo
from app.ingest.extractores import extrair_texto
from app.ingest.fontes import hash_bytes, obter_fonte
from app.ingest.identidade import chave_estavel, extrair_periodo
from app.ingest.normalizador import normalizar_texto


@dataclass
class ResumoSync:
    processados: int = 0
    ignorados: int = 0
    erros: int = 0
    itens_inseridos: int = 0
    reconciliados: list = None


def sincronizar(limite: int | None = None, apenas: set[str] | None = None,
                forcar: bool = False, verbose: bool = True) -> ResumoSync:
    fonte = obter_fonte()
    arquivos = fonte.listar()

    # agrupa por chave estável, mantendo o mais recente (por data de modificação)
    por_chave: dict = {}
    for a in arquivos:
        ch = chave_estavel(a.nome)
        atual = por_chave.get(ch)
        if atual is None or (a.modificado_em or "") > (atual.modificado_em or ""):
            por_chave[ch] = a

    chaves_presentes = set(por_chave.keys())

    # seleção (para testes: apenas certas chaves e/ou um limite)
    itens = list(por_chave.items())
    if apenas:
        itens = [(c, a) for c, a in itens if c in apenas]
    if limite:
        itens = itens[:limite]

    resumo = ResumoSync(reconciliados=[])

    for chave, a in itens:
        raw = fonte.baixar(a)
        h = hash_bytes(raw)
        periodo = extrair_periodo(a.nome)

        if not forcar and repo.hash_ja_processado(a.nome, h):
            resumo.ignorados += 1
            if verbose:
                print(f"  = {chave:18} ignorado (sem mudança)")
            continue

        try:
            texto = extrair_texto(a.nome, raw)
            res = normalizar_texto(texto, a.nome, marca_hint=chave.upper())
            if not res.itens:
                raise ValueError("nenhum item extraído")
        except Exception as e:
            repo.registrar_erro(a.nome, f"{e.__class__.__name__}: {e}",
                                drive_file_id=a.id, hash_arquivo=h, periodo=periodo)
            resumo.erros += 1
            if verbose:
                print(f"  ! {chave:18} ERRO: {e}")
            continue

        _, qtd = repo.substituir_estoque(
            a.nome, res.itens,
            empresa=res.empresa_fonte, cnpj=res.cnpj,
            data_referencia=res.data_referencia,
            drive_file_id=a.id, hash_arquivo=h, periodo=periodo,
        )
        resumo.processados += 1
        resumo.itens_inseridos += qtd
        if verbose:
            print(f"  + {chave:18} {qtd:5} itens  (empresa: {res.empresa_fonte})")

    # reconciliação só em execução completa (não em teste limitado)
    if not apenas and not limite:
        resumo.reconciliados = repo.reconciliar(chaves_presentes)

    return resumo
