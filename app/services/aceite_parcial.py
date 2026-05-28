"""Helpers de aceite parcial (lanchonete recusa fornecedor especifico).

Centraliza as queries de "fornecedor X foi recusado pela lanchonete Y na
rodada Z?" pra calculos (CMV, P&L, pagamento) e fluxo (fornecedor nao
deve confirmar pagamento de lanchonete que o recusou).

Modelo: app.models.RecusaFornecedor — 1 linha por (rodada, lanchonete,
fornecedor) recusado. Ausencia = aceito.
"""
from __future__ import annotations

from app import db
from app.models import RecusaFornecedor


def fornecedor_recusado(rodada_id: int, lanchonete_id: int,
                         fornecedor_id: int) -> bool:
    """True se a lanchonete recusou esse fornecedor especifico nessa rodada."""
    return db.session.query(
        db.session.query(RecusaFornecedor.id)
        .filter_by(rodada_id=rodada_id, lanchonete_id=lanchonete_id,
                   fornecedor_id=fornecedor_id)
        .exists()
    ).scalar()


def fornecedores_recusados_por_lanchonete(rodada_id: int,
                                            lanchonete_id: int) -> set[int]:
    """IDs dos fornecedores que a lanchonete recusou nessa rodada."""
    rows = (
        db.session.query(RecusaFornecedor.fornecedor_id)
        .filter_by(rodada_id=rodada_id, lanchonete_id=lanchonete_id)
        .all()
    )
    return {r[0] for r in rows}


def lanchonetes_que_recusaram(rodada_id: int, fornecedor_id: int) -> set[int]:
    """IDs das lanchonetes que recusaram esse fornecedor nessa rodada.
    Usado pra filtrar dashboard de pendencias do fornecedor."""
    rows = (
        db.session.query(RecusaFornecedor.lanchonete_id)
        .filter_by(rodada_id=rodada_id, fornecedor_id=fornecedor_id)
        .all()
    )
    return {r[0] for r in rows}


def registrar_recusas(rodada_id: int, lanchonete_id: int,
                       fornecedor_ids: list[int]) -> int:
    """Insere uma linha de RecusaFornecedor pra cada fornecedor da lista.

    Idempotente: se ja existe linha (rodada, lanchonete, forn), pula.
    Retorna a quantidade de recusas EFETIVAMENTE inseridas (novas).
    Caller deve dar commit.
    """
    if not fornecedor_ids:
        return 0
    ja_recusados = fornecedores_recusados_por_lanchonete(rodada_id, lanchonete_id)
    novos = 0
    for fid in fornecedor_ids:
        if fid in ja_recusados:
            continue
        db.session.add(RecusaFornecedor(
            rodada_id=rodada_id,
            lanchonete_id=lanchonete_id,
            fornecedor_id=fid,
        ))
        novos += 1
    return novos
