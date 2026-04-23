"""Listagem + export CSV das rodadas da lanchonete logada."""
from flask import render_template, request
from flask_login import login_required, current_user
from sqlalchemy import func

from app import db
from app.models import Rodada, ItemPedido, ParticipacaoRodada
from app.services.csv_export import csv_response
from . import historico_bp, lanchonete_required, STATUS_HISTORICO


@historico_bp.route("/")
@login_required
@lanchonete_required
def listar():
    """Listagem de rodadas em que a lanchonete logada participou."""
    lanchonete = current_user.lanchonete
    filtro_status = request.args.get("status", "todas")

    rodadas_q = (
        db.session.query(
            Rodada,
            func.count(ItemPedido.id).label("qtd_itens"),
            func.count(func.distinct(ItemPedido.produto_id)).label("qtd_produtos"),
        )
        .join(ItemPedido, ItemPedido.rodada_id == Rodada.id)
        .filter(ItemPedido.lanchonete_id == lanchonete.id)
        .group_by(Rodada.id)
        .order_by(Rodada.data_abertura.desc())
    )

    notas_map = dict(
        db.session.query(ParticipacaoRodada.rodada_id,
                         ParticipacaoRodada.avaliacao_geral)
        .filter(ParticipacaoRodada.lanchonete_id == lanchonete.id,
                ParticipacaoRodada.avaliacao_geral.isnot(None))
        .all()
    )

    if filtro_status == "todas":
        pass
    elif filtro_status in STATUS_HISTORICO:
        rodadas_q = rodadas_q.filter(Rodada.status == filtro_status)
    elif filtro_status == "aberta":
        rodadas_q = rodadas_q.filter(Rodada.status == "aberta")

    rodadas = rodadas_q.all()

    contagem = dict(
        db.session.query(Rodada.status, func.count(func.distinct(Rodada.id)))
        .join(ItemPedido, ItemPedido.rodada_id == Rodada.id)
        .filter(ItemPedido.lanchonete_id == lanchonete.id)
        .group_by(Rodada.status)
        .all()
    )
    contagem["todas"] = sum(contagem.values())

    return render_template(
        "historico/listar.html",
        rodadas=rodadas,
        filtro_status=filtro_status,
        contagem=contagem,
        lanchonete=lanchonete,
        notas_map=notas_map,
    )


@historico_bp.route("/exportar.csv")
@login_required
@lanchonete_required
def exportar():
    """Exporta histórico de rodadas da lanchonete logada."""
    lanchonete = current_user.lanchonete

    rodadas = (
        db.session.query(
            Rodada,
            func.count(ItemPedido.id).label("qtd_itens"),
        )
        .join(ItemPedido, ItemPedido.rodada_id == Rodada.id)
        .filter(ItemPedido.lanchonete_id == lanchonete.id)
        .group_by(Rodada.id)
        .order_by(Rodada.data_abertura.desc())
        .all()
    )
    notas = dict(
        db.session.query(ParticipacaoRodada.rodada_id, ParticipacaoRodada.avaliacao_geral)
        .filter(ParticipacaoRodada.lanchonete_id == lanchonete.id,
                ParticipacaoRodada.avaliacao_geral.isnot(None))
        .all()
    )
    return csv_response(
        filename=f"minhas_rodadas_{lanchonete.nome_fantasia.replace(' ', '_')}.csv",
        headers=["rodada", "data", "status", "itens_pedidos", "avaliacao"],
        rows=[
            [r.nome, r.data_abertura.strftime("%Y-%m-%d"), r.status,
             str(qtd), str(notas.get(r.id, ""))]
            for r, qtd in rodadas
        ],
    )
