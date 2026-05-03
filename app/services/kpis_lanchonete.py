"""KPIs da lanchonete com cache (espelha kpis_admin.py + kpis_fornecedor.py).

Reduz carga no DB pro dashboard da lanchonete (recarregado a cada login,
muitas vezes ao dia em multi-tenant). Trade-off: ate 30s de atraso —
aceitavel pra contagens/medias do painel executivo.
"""
from sqlalchemy import func

from app import db, cache
from app.models import ItemPedido, ParticipacaoRodada


@cache.memoize(timeout=30)
def total_rodadas_participadas(lanchonete_id: int) -> int:
    """Quantas rodadas DISTINTAS a lanchonete participou (>=1 ItemPedido)."""
    return db.session.scalar(
        db.select(func.count(func.distinct(ItemPedido.rodada_id)))
        .where(ItemPedido.lanchonete_id == lanchonete_id)
    ) or 0


@cache.memoize(timeout=30)
def rodadas_concluidas(lanchonete_id: int) -> int:
    """Rodadas com avaliacao_geral preenchida pela lanchonete."""
    return (
        ParticipacaoRodada.query
        .filter_by(lanchonete_id=lanchonete_id)
        .filter(ParticipacaoRodada.avaliacao_geral.isnot(None))
        .count()
    )


@cache.memoize(timeout=30)
def media_avaliacao_dada(lanchonete_id: int) -> float:
    """Media das notas que a lanchonete deu nas rodadas (0 se nunca)."""
    media = (
        db.session.query(func.avg(ParticipacaoRodada.avaliacao_geral))
        .filter(ParticipacaoRodada.lanchonete_id == lanchonete_id,
                ParticipacaoRodada.avaliacao_geral.isnot(None))
        .scalar()
    )
    return round(float(media), 1) if media else 0.0
