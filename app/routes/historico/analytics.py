"""Meu Resumo (KPIs de avaliacoes) + Meu CMV (gasto e economia)."""
from flask import render_template
from flask_login import login_required, current_user
from sqlalchemy import func

from app import db
from app.models import (
    Rodada, ItemPedido, Produto, Fornecedor,
    ParticipacaoRodada, AvaliacaoRodada,
)
from app.services.cmv_lanchonete import calcular_cmv
from . import historico_bp, lanchonete_required


@historico_bp.route("/analytics")
@login_required
@lanchonete_required
def analytics():
    """Dashboard de KPIs pessoais da lanchonete logada."""
    lanchonete = current_user.lanchonete
    lid = lanchonete.id

    total_rodadas = (
        db.session.query(func.count(func.distinct(ItemPedido.rodada_id)))
        .filter(ItemPedido.lanchonete_id == lid)
        .scalar()
    ) or 0

    rodadas_avaliadas = (
        ParticipacaoRodada.query
        .filter_by(lanchonete_id=lid)
        .filter(ParticipacaoRodada.avaliacao_geral.isnot(None))
        .count()
    )

    total_itens_pedidos = ItemPedido.query.filter_by(lanchonete_id=lid).count()

    minha_media = (
        db.session.query(func.avg(ParticipacaoRodada.avaliacao_geral))
        .filter(ParticipacaoRodada.lanchonete_id == lid,
                ParticipacaoRodada.avaliacao_geral.isnot(None))
        .scalar()
    ) or 0

    meus_top_produtos = (
        db.session.query(
            Produto.nome, Produto.unidade,
            func.sum(ItemPedido.quantidade).label("total"),
        )
        .join(ItemPedido, ItemPedido.produto_id == Produto.id)
        .filter(ItemPedido.lanchonete_id == lid)
        .group_by(Produto.id)
        .order_by(func.sum(ItemPedido.quantidade).desc())
        .limit(5)
        .all()
    )

    meus_fornecedores = (
        db.session.query(
            Fornecedor.razao_social,
            func.avg(AvaliacaoRodada.estrelas).label("media"),
            func.count(AvaliacaoRodada.id).label("avaliacoes"),
        )
        .join(AvaliacaoRodada, AvaliacaoRodada.fornecedor_id == Fornecedor.id)
        .filter(AvaliacaoRodada.lanchonete_id == lid)
        .group_by(Fornecedor.id)
        .order_by(func.avg(AvaliacaoRodada.estrelas).desc())
        .all()
    )

    historico_notas = (
        db.session.query(
            Rodada.nome,
            ParticipacaoRodada.avaliacao_geral,
        )
        .join(ParticipacaoRodada, ParticipacaoRodada.rodada_id == Rodada.id)
        .filter(ParticipacaoRodada.lanchonete_id == lid,
                ParticipacaoRodada.avaliacao_geral.isnot(None))
        .order_by(Rodada.data_abertura.desc())
        .limit(10)
        .all()
    )

    return render_template(
        "historico/analytics.html",
        lanchonete=lanchonete,
        total_rodadas=total_rodadas,
        rodadas_avaliadas=rodadas_avaliadas,
        total_itens_pedidos=total_itens_pedidos,
        minha_media=round(float(minha_media), 1),
        meus_top_produtos=meus_top_produtos,
        meus_fornecedores=meus_fornecedores,
        historico_notas=historico_notas,
    )


@historico_bp.route("/cmv")
@login_required
@lanchonete_required
def cmv():
    """Meu CMV: gasto efetivo em compras aceitas, economia, top categorias/produtos."""
    lanchonete = current_user.lanchonete
    dados = calcular_cmv(lanchonete.id)

    return render_template(
        "historico/cmv.html",
        lanchonete=lanchonete,
        kpis=dados["kpis"],
        top_categorias=dados["top_categorias"],
        top_produtos=dados["top_produtos"],
        por_rodada=dados["por_rodada"],
    )
