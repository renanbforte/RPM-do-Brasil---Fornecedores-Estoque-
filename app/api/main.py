"""
API de consulta de estoque (FastAPI) — consumida pelo agente do Dify.

- Abre o SQLite em SOMENTE-LEITURA (mode=ro).
- Busca de material/marca é parcial e tolerante (usa os campos normalizados).
- Autenticação por header `Authorization: Bearer <token>` (token = API_TOKEN).
- `/health` é público (para o health check do EasyPanel).
"""
from __future__ import annotations

import secrets
import sqlite3
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Query

from app.core import config
from app.core.normalizacao import normalizar

app = FastAPI(
    title="API de Estoque de Fornecedores",
    description="Consulta de estoque de rolamentos por material, marca e fornecedor.",
    version="1.0.0",
)


# --------------------------------------------------------------------------
# Conexão somente-leitura (uma por requisição)
# --------------------------------------------------------------------------
def _conectar_ro() -> sqlite3.Connection:
    uri = f"file:{Path(config.DATABASE_PATH).as_posix()}?mode=ro"
    con = sqlite3.connect(uri, uri=True, check_same_thread=False)
    con.row_factory = sqlite3.Row
    return con


# --------------------------------------------------------------------------
# Autenticação: Authorization: Bearer <token>
# --------------------------------------------------------------------------
def verificar_token(authorization: str | None = Header(default=None)) -> None:
    if not config.API_TOKEN:
        # falha fechada: sem token configurado no servidor, ninguém entra
        raise HTTPException(status_code=503, detail="API_TOKEN não configurada no servidor")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Token ausente ou malformado")
    enviado = authorization.split(" ", 1)[1].strip()
    if not secrets.compare_digest(enviado, config.API_TOKEN):
        raise HTTPException(status_code=401, detail="Token inválido")


# --------------------------------------------------------------------------
# Helpers de query
# --------------------------------------------------------------------------
def _cond_material(material: str) -> tuple[str, list[str]]:
    """Cada palavra normalizada precisa aparecer em material_normalizado (AND)."""
    termos = normalizar(material).split()
    if not termos:
        return "1=1", []
    cond = " AND ".join(["material_normalizado LIKE ?"] * len(termos))
    params = [f"%{t}%" for t in termos]
    return cond, params


def _linha_item(r: sqlite3.Row) -> dict:
    return {
        "fornecedor": r["slug"],
        "empresa_fonte": r["empresa_fonte"],
        "codigo": r["codigo_fornecedor"],
        "material": r["material_original"],
        "marca": r["marca"],
        "quantidade": r["quantidade"],
        "unidade": r["unidade"],
        "data_referencia": r["data_referencia"],
    }


# --------------------------------------------------------------------------
# Endpoints
# --------------------------------------------------------------------------
@app.get("/health")
def health() -> dict:
    """Health check público (sem autenticação)."""
    return {"status": "ok"}


@app.get("/estoque", dependencies=[Depends(verificar_token)])
def get_estoque(
    material: str = Query(..., min_length=1, description="Texto do material/part-number"),
    marca: str | None = Query(default=None, description="Filtro opcional por marca"),
    limite: int = Query(default=50, ge=1, le=500),
) -> list[dict]:
    """Quais fornecedores têm o material X (e quanto cada um tem)."""
    cond_mat, params = _cond_material(material)
    sql = (
        "SELECT f.slug, f.empresa_fonte, e.codigo_fornecedor, e.material_original, "
        "e.marca, e.quantidade, e.unidade, e.data_referencia "
        "FROM estoque e JOIN fornecedores f ON f.id = e.fornecedor_id "
        f"WHERE {cond_mat}"
    )
    if marca:
        sql += " AND e.marca_normalizada LIKE ?"
        params.append(f"%{normalizar(marca)}%")
    sql += " ORDER BY e.quantidade DESC LIMIT ?"
    params.append(limite)

    con = _conectar_ro()
    try:
        return [_linha_item(r) for r in con.execute(sql, params)]
    finally:
        con.close()


@app.get("/fornecedores", dependencies=[Depends(verificar_token)])
def get_fornecedores() -> list[dict]:
    """Lista as fontes/fornecedores com contagem de itens e última atualização."""
    sql = (
        "SELECT f.slug, f.nome_canonico, f.empresa_fonte, "
        "COUNT(e.id) AS itens, "
        "(SELECT MAX(i.finalizado_em) FROM ingestoes i "
        "  WHERE i.fornecedor_id = f.id AND i.status = 'sucesso') AS ultima_atualizacao "
        "FROM fornecedores f LEFT JOIN estoque e ON e.fornecedor_id = f.id "
        "GROUP BY f.id ORDER BY itens DESC"
    )
    con = _conectar_ro()
    try:
        return [
            {
                "fornecedor": r["slug"],
                "nome": r["nome_canonico"],
                "empresa_fonte": r["empresa_fonte"],
                "itens": r["itens"],
                "ultima_atualizacao": r["ultima_atualizacao"],
            }
            for r in con.execute(sql)
        ]
    finally:
        con.close()


@app.get("/fornecedores/{slug}/estoque", dependencies=[Depends(verificar_token)])
def get_estoque_fornecedor(
    slug: str,
    material: str | None = Query(default=None, description="Filtro opcional por material"),
    limite: int = Query(default=200, ge=1, le=1000),
) -> list[dict]:
    """Estoque de um fornecedor específico (o fornecedor Y tem o material X?)."""
    con = _conectar_ro()
    try:
        forn = con.execute("SELECT id FROM fornecedores WHERE slug = ?", (slug,)).fetchone()
        if not forn:
            raise HTTPException(status_code=404, detail=f"Fornecedor não encontrado: {slug}")

        sql = (
            "SELECT f.slug, f.empresa_fonte, e.codigo_fornecedor, e.material_original, "
            "e.marca, e.quantidade, e.unidade, e.data_referencia "
            "FROM estoque e JOIN fornecedores f ON f.id = e.fornecedor_id "
            "WHERE e.fornecedor_id = ?"
        )
        params: list = [forn["id"]]
        if material:
            cond_mat, mat_params = _cond_material(material)
            sql += f" AND {cond_mat}"
            params.extend(mat_params)
        sql += " ORDER BY e.quantidade DESC LIMIT ?"
        params.append(limite)

        return [_linha_item(r) for r in con.execute(sql, params)]
    finally:
        con.close()


@app.get("/status", dependencies=[Depends(verificar_token)])
def get_status() -> list[dict]:
    """Última ingestão de cada fornecedor (status, quantidade, data)."""
    sql = (
        "SELECT f.slug, i.status, i.qtd_registros, i.periodo, i.finalizado_em "
        "FROM ingestoes i JOIN fornecedores f ON f.id = i.fornecedor_id "
        "WHERE i.id IN (SELECT MAX(id) FROM ingestoes GROUP BY fornecedor_id) "
        "ORDER BY i.finalizado_em DESC"
    )
    con = _conectar_ro()
    try:
        return [
            {
                "fornecedor": r["slug"],
                "status": r["status"],
                "qtd_registros": r["qtd_registros"],
                "periodo": r["periodo"],
                "finalizado_em": r["finalizado_em"],
            }
            for r in con.execute(sql)
        ]
    finally:
        con.close()
