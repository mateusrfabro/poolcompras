"""Logica do painel da lanchonete: KPIs + ultimas rodadas + pedido atual."""
from sqlalchemy import func
from app import db
from app.models import ItemPedido, ParticipacaoRodada, Rodada, Cotacao
from app.services.pendencias import pendencias_lanchonete


def dashboard_data(lanchonete_id):
    """Retorna dict com tudo que o template do dashboard precisa.

    Returns:
        {
            'pendencias': list,
            'kpis': dict (total_rodadas, rodadas_concluidas, pendencias, media_que_deu),
            'ultimas_rodadas': list of {rodada, total, nota},
        }
    """
    pendencias = pendencias_lanchonete(lanchonete_id)

    total_rodadas = (
        db.session.query(func.count(func.distinct(ItemPedido.rodada_id)))
        .filter(ItemPedido.lanchonete_id == lanchonete_id)
        .scalar()
    ) or 0

    rodadas_concluidas = (
        ParticipacaoRodada.query
        .filter_by(lanchonete_id=lanchonete_id)
        .filter(ParticipacaoRodada.avaliacao_geral.isnot(None))
        .count()
    )

    media_que_deu = (
        db.session.query(func.avg(ParticipacaoRodada.avaliacao_geral))
        .filter(ParticipacaoRodada.lanchonete_id == lanchonete_id,
                ParticipacaoRodada.avaliacao_geral.isnot(None))
        .scalar()
    ) or 0

    kpis = {
        "total_rodadas": total_rodadas,
        "rodadas_concluidas": rodadas_concluidas,
        "pendencias": len(pendencias),
        "media_que_deu": round(float(media_que_deu), 1),
    }

    # Ultimas 3 rodadas finalizadas com preview (total gasto + nota dada)
    ultimas_raw = (
        db.session.query(Rodada)
        .join(ItemPedido, ItemPedido.rodada_id == Rodada.id)
        .filter(ItemPedido.lanchonete_id == lanchonete_id,
                Rodada.status.in_(["finalizada", "cancelada", "fechada"]))
        .group_by(Rodada.id)
        .order_by(Rodada.data_abertura.desc())
        .limit(3)
        .all()
    )

    ultimas_rodadas = []
    for r in ultimas_raw:
        total = (
            db.session.query(
                func.coalesce(func.sum(ItemPedido.quantidade * Cotacao.preco_unitario), 0)
            )
            .join(Cotacao,
                  (Cotacao.rodada_id == ItemPedido.rodada_id) &
                  (Cotacao.produto_id == ItemPedido.produto_id) &
                  (Cotacao.selecionada.is_(True)))
            .filter(ItemPedido.rodada_id == r.id,
                    ItemPedido.lanchonete_id == lanchonete_id)
            .scalar()
        ) or 0
        part = (
            ParticipacaoRodada.query
            .filter_by(rodada_id=r.id, lanchonete_id=lanchonete_id)
            .first()
        )
        nota = part.avaliacao_geral if part else None
        ultimas_rodadas.append({
            "rodada": r,
            "total": float(total) if total else 0.0,
            "nota": nota,
        })

    return {
        "pendencias": pendencias,
        "kpis": kpis,
        "ultimas_rodadas": ultimas_rodadas,
    }
