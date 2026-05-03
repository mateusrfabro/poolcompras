"""KPIs do fornecedor com cache (espelha kpis_admin.py).

Reduz carga no DB pros dashboards do fornecedor que sao recarregados
frequentemente (dashboard, analytics). Trade-off: numeros podem ficar
ate 30s desatualizados — aceitavel pra dashboard executivo.

Em testing CACHE_TYPE='NullCache' garante que cada teste le dado fresco.
"""
from sqlalchemy import func

from app import db, cache
from app.models import Cotacao, AvaliacaoRodada


@cache.memoize(timeout=30)
def total_cotacoes(fornecedor_id: int) -> int:
    """Total de cotacoes que o fornecedor enviou (qualquer rodada)."""
    return Cotacao.query.filter_by(fornecedor_id=fornecedor_id).count()


@cache.memoize(timeout=30)
def cotacoes_vencedoras(fornecedor_id: int) -> int:
    """Cotacoes do fornecedor marcadas como selecionada=True."""
    return Cotacao.query.filter_by(
        fornecedor_id=fornecedor_id, selecionada=True,
    ).count()


@cache.memoize(timeout=30)
def media_avaliacao_recebida(fornecedor_id: int) -> float:
    """Media de estrelas recebidas pelo fornecedor (0 se nunca avaliado)."""
    media = (
        db.session.query(func.avg(AvaliacaoRodada.estrelas))
        .filter(AvaliacaoRodada.fornecedor_id == fornecedor_id)
        .scalar()
    )
    return round(float(media), 1) if media else 0.0


@cache.memoize(timeout=30)
def total_avaliacoes_recebidas(fornecedor_id: int) -> int:
    """Quantas avaliacoes o fornecedor recebeu."""
    return AvaliacaoRodada.query.filter_by(fornecedor_id=fornecedor_id).count()
