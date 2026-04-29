"""KPIs do dashboard admin com cache de 30s.

Reduz carga no DB em telas que admin recarrega frequentemente. Trade-off:
numeros podem ficar 30s desatualizados — aceitavel pra dashboard executivo.

Em testing CACHE_TYPE='NullCache' garante que cada teste le dado fresco.
"""
from sqlalchemy import select, func

from app import db, cache
from app.models import Lanchonete, Produto, ItemPedido


@cache.cached(timeout=30, key_prefix='kpi_total_lanchonetes')
def total_lanchonetes_ativas() -> int:
    return db.session.scalar(
        select(func.count(Lanchonete.id)).where(Lanchonete.ativa.is_(True))
    ) or 0


@cache.cached(timeout=30, key_prefix='kpi_total_produtos')
def total_produtos_ativos() -> int:
    return db.session.scalar(
        select(func.count(Produto.id)).where(Produto.ativo.is_(True))
    ) or 0


@cache.memoize(timeout=30)
def pedidos_da_rodada(rodada_id: int) -> int:
    """Total de itens pedidos numa rodada. Memoize cacheia por rodada_id."""
    return db.session.scalar(
        select(func.count(ItemPedido.id))
        .where(ItemPedido.rodada_id == rodada_id)
    ) or 0


@cache.memoize(timeout=30)
def qtd_lanchonetes_da_rodada(rodada_id: int) -> int:
    """Lanchonetes distintas que pediram numa rodada."""
    return db.session.scalar(
        select(func.count(func.distinct(ItemPedido.lanchonete_id)))
        .where(ItemPedido.rodada_id == rodada_id)
    ) or 0
