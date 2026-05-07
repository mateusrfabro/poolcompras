"""Servicos do CRM: agregacao do Kanban + KPIs por vendedor.

Fonte unica das queries quentes do CRM. Centralizar aqui evita drift
entre rota Kanban e detalhe do lead.
"""
from __future__ import annotations

from collections import OrderedDict
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import joinedload

from app import db
from app.models import Lead, Vendedor


def leads_agrupados(vendedor_id: int | None = None) -> dict[str, list[Lead]]:
    """Retorna OrderedDict {status: [Lead, ...]} pra renderizar o Kanban.

    Args:
        vendedor_id: se setado, filtra. Se None, todos os leads (admin).

    Ordem das chaves segue STATUS_KANBAN_ORDEM. Cada bucket vem ordenado
    por atualizado_em DESC (cards mais recentemente mexidos no topo).
    """
    q = (
        select(Lead)
        .options(joinedload(Lead.vendedor))
        .order_by(Lead.atualizado_em.desc())
    )
    if vendedor_id is not None:
        q = q.where(Lead.vendedor_id == vendedor_id)

    leads = db.session.scalars(q).all()
    grupos: dict[str, list[Lead]] = OrderedDict(
        (s, []) for s in Lead.STATUS_KANBAN_ORDEM
    )
    for lead in leads:
        grupos.setdefault(lead.status, []).append(lead)
    return grupos


def kpis_vendedores(vendedor_id: int | None = None) -> list[dict]:
    """Meta vs realizado por vendedor no mes corrente.

    Realizado = leads que viraram fechado neste mes (atualizado_em ja
    aponta pra ultima mudanca de status; pra MVP eh boa aproximacao).

    Returns:
        [{vendedor_id, nome, meta, fechados_mes, pct}]
    """
    agora = datetime.now(timezone.utc)
    inicio_mes = datetime(agora.year, agora.month, 1, tzinfo=timezone.utc)

    q_vend = select(Vendedor).where(Vendedor.ativo.is_(True))
    if vendedor_id is not None:
        q_vend = q_vend.where(Vendedor.id == vendedor_id)
    vendedores = db.session.scalars(q_vend.order_by(Vendedor.nome)).all()

    resultado = []
    for v in vendedores:
        fechados = db.session.scalar(
            select(func.count(Lead.id))
            .where(Lead.vendedor_id == v.id)
            .where(Lead.status == Lead.STATUS_FECHADO)
            .where(Lead.atualizado_em >= inicio_mes)
        ) or 0
        meta = v.meta_mensal_clientes
        pct = round(fechados / meta * 100, 1) if meta > 0 else 0
        resultado.append({
            "vendedor_id": v.id,
            "nome": v.nome,
            "meta": meta,
            "fechados_mes": fechados,
            "pct": pct,
        })
    return resultado
