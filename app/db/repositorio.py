"""
Operações de banco do pipeline: identidade do fornecedor, gravação ATÔMICA
do estoque, log de ingestão e reconciliação da pasta.
"""
from __future__ import annotations

from app.core.normalizacao import normalizar
from app.db.connection import conectar
from app.ingest.identidade import chave_estavel, rotulo_exibicao

# similaridade mínima (0-100) para tratar dois nomes como a MESMA fonte (typo)
LIMIAR_FUZZY = 92


# --------------------------------------------------------------------------
# Identidade do fornecedor (chave estável + aliases + fuzzy)
# --------------------------------------------------------------------------
def _achar_fornecedor(con, chave: str) -> int | None:
    row = con.execute("SELECT id FROM fornecedores WHERE slug = ?", (chave,)).fetchone()
    if row:
        return row["id"]

    row = con.execute(
        "SELECT fornecedor_id FROM fornecedor_aliases WHERE alias_normalizado = ?",
        (chave,),
    ).fetchone()
    if row:
        return row["fornecedor_id"]

    # fuzzy: pega o slug mais parecido acima do limiar (tolera 1 letra trocada)
    from rapidfuzz import fuzz, process

    existentes = [(r["id"], r["slug"]) for r in con.execute("SELECT id, slug FROM fornecedores")]
    if existentes:
        nomes = [s for _, s in existentes]
        m = process.extractOne(chave, nomes, scorer=fuzz.ratio)
        if m and m[1] >= LIMIAR_FUZZY:
            return existentes[m[2]][0]
    return None


def obter_ou_criar_fornecedor(con, nome_arquivo: str,
                              empresa: str | None = None,
                              cnpj: str | None = None) -> int:
    """Resolve (ou cria) o fornecedor pela chave estável do nome do arquivo."""
    chave = chave_estavel(nome_arquivo)
    fid = _achar_fornecedor(con, chave)

    if fid is None:
        cur = con.execute(
            "INSERT INTO fornecedores (nome_canonico, slug, empresa_fonte, cnpj) "
            "VALUES (?, ?, ?, ?)",
            (rotulo_exibicao(nome_arquivo), chave, empresa, cnpj),
        )
        fid = cur.lastrowid
    else:
        # substituição atômica = refresh completo da fonte: a empresa/cnpj do
        # conteúdo ATUAL passam a valer (inclusive limpando um valor errado antigo).
        con.execute(
            "UPDATE fornecedores SET empresa_fonte = ?, cnpj = ?, "
            "atualizado_em = datetime('now') WHERE id = ?",
            (empresa, cnpj, fid),
        )

    # guarda a variação de nome vista (histórico de aliases)
    con.execute(
        "INSERT OR IGNORE INTO fornecedor_aliases (fornecedor_id, alias_normalizado, origem) "
        "VALUES (?, ?, 'arquivo')",
        (fid, chave),
    )
    return fid


# --------------------------------------------------------------------------
# Gravação ATÔMICA: DELETE do fornecedor + INSERT dos novos (tudo ou nada)
# --------------------------------------------------------------------------
def substituir_estoque(nome_arquivo: str, itens: list,
                       empresa: str | None, cnpj: str | None,
                       data_referencia: str | None,
                       drive_file_id: str | None, hash_arquivo: str | None,
                       periodo: str | None) -> tuple[int, int]:
    """
    Substitui TODO o estoque do fornecedor pelos novos itens, numa transação.
    Em caso de erro faz rollback — o estoque antigo permanece intacto.
    Retorna (fornecedor_id, qtd_inserida).
    """
    with conectar() as con:
        try:
            fid = obter_ou_criar_fornecedor(con, nome_arquivo, empresa, cnpj)

            con.execute("DELETE FROM estoque WHERE fornecedor_id = ?", (fid,))

            filas = [
                (
                    fid, it.codigo, it.material, normalizar(it.material),
                    it.marca, (normalizar(it.marca) or None),
                    it.quantidade, it.unidade, data_referencia, nome_arquivo,
                )
                for it in itens
            ]
            con.executemany(
                "INSERT INTO estoque (fornecedor_id, codigo_fornecedor, material_original, "
                "material_normalizado, marca, marca_normalizada, quantidade, unidade, "
                "data_referencia, arquivo_origem) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                filas,
            )
            con.execute(
                "INSERT INTO ingestoes (fornecedor_id, arquivo, drive_file_id, hash_arquivo, "
                "periodo, status, qtd_registros, finalizado_em) "
                "VALUES (?, ?, ?, ?, ?, 'sucesso', ?, datetime('now'))",
                (fid, nome_arquivo, drive_file_id, hash_arquivo, periodo, len(filas)),
            )
            con.commit()
            return fid, len(filas)
        except Exception:
            con.rollback()
            raise


def registrar_erro(nome_arquivo: str, erro: str, drive_file_id: str | None = None,
                   hash_arquivo: str | None = None, periodo: str | None = None) -> None:
    """Registra uma ingestão com erro, SEM tocar no estoque existente."""
    chave = chave_estavel(nome_arquivo)
    with conectar() as con:
        r = con.execute("SELECT id FROM fornecedores WHERE slug = ?", (chave,)).fetchone()
        con.execute(
            "INSERT INTO ingestoes (fornecedor_id, arquivo, drive_file_id, hash_arquivo, "
            "periodo, status, erro, finalizado_em) "
            "VALUES (?, ?, ?, ?, ?, 'erro', ?, datetime('now'))",
            (r["id"] if r else None, nome_arquivo, drive_file_id, hash_arquivo, periodo, erro[:1000]),
        )
        con.commit()


def hash_ja_processado(nome_arquivo: str, hash_arquivo: str) -> bool:
    """True se este conteúdo (hash) já foi ingerido com sucesso para esta fonte."""
    chave = chave_estavel(nome_arquivo)
    with conectar() as con:
        r = con.execute(
            "SELECT 1 FROM ingestoes i JOIN fornecedores f ON f.id = i.fornecedor_id "
            "WHERE f.slug = ? AND i.hash_arquivo = ? AND i.status = 'sucesso' LIMIT 1",
            (chave, hash_arquivo),
        ).fetchone()
        return r is not None


def reconciliar(chaves_presentes: set[str]) -> list[tuple[str, int]]:
    """
    Remove o estoque de fornecedores cuja chave NÃO está mais na pasta.
    Mantém o cadastro do fornecedor (histórico). Retorna [(slug, qtd_removida)].
    """
    removidos: list[tuple[str, int]] = []
    with conectar() as con:
        for r in con.execute("SELECT id, slug FROM fornecedores").fetchall():
            if r["slug"] in chaves_presentes:
                continue
            n = con.execute(
                "SELECT COUNT(*) c FROM estoque WHERE fornecedor_id = ?", (r["id"],)
            ).fetchone()["c"]
            if n:
                con.execute("DELETE FROM estoque WHERE fornecedor_id = ?", (r["id"],))
                removidos.append((r["slug"], n))
        con.commit()
    return removidos
