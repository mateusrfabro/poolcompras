"""Acoes do fornecedor no fluxo pos-finalizacao: confirmar pagamento, informar entrega."""
from datetime import datetime, date, timedelta
from flask import request, redirect, url_for, flash, abort
from flask_login import login_required, current_user
from sqlalchemy.exc import SQLAlchemyError

from app import db, limiter
from app.models import ParticipacaoRodada, EventoRodada, Lanchonete
from app.services.notificacoes import notificar_evento
from . import (
    fluxo_bp, _agora, _registrar_evento,
    _so_fornecedor_da_rodada, _fornecedor_atende_lanchonete,
)


@fluxo_bp.route("/rodada/<int:rodada_id>/lanchonete/<int:lanchonete_id>/pagamento",
                methods=["POST"])
@login_required
@limiter.limit("60 per hour")
def confirmar_pagamento(rodada_id, lanchonete_id):
    rodada, _fornecedor = _so_fornecedor_da_rodada(rodada_id)
    # Ownership: fornecedor so confirma pagamento de lanchonete cujos itens ele venceu.
    if not _fornecedor_atende_lanchonete(rodada_id, _fornecedor.id, lanchonete_id):
        abort(403)
    p = ParticipacaoRodada.query.filter_by(
        rodada_id=rodada_id, lanchonete_id=lanchonete_id,
    ).first_or_404()
    if not p.comprovante_key:
        flash("Cliente ainda não enviou o comprovante.", "error")
        return redirect(url_for("fornecedor.dashboard"))
    if p.pagamento_confirmado_em:
        flash("Pagamento já foi confirmado anteriormente.", "warning")
        return redirect(url_for("fornecedor.dashboard"))

    try:
        p.pagamento_confirmado_em = _agora()
        p.pagamento_confirmado_por_id = current_user.id
        _registrar_evento(rodada_id, EventoRodada.TIPO_PAGAMENTO_CONFIRMADO,
                          "Fornecedor confirmou recebimento do pagamento",
                          lanchonete_id=lanchonete_id, ator_id=current_user.id)
        db.session.commit()

        lanch = db.session.get(Lanchonete, lanchonete_id)
        if lanch and lanch.responsavel:
            notificar_evento(
                lanch.responsavel,
                "Pagamento confirmado",
                f"{_fornecedor.razao_social} confirmou o recebimento do seu "
                f"pagamento na rodada '{rodada.nome}'. Aguardando informacao "
                f"de entrega.",
            )

        flash("Pagamento confirmado.", "success")
    except SQLAlchemyError:
        db.session.rollback()
        flash("Erro ao confirmar pagamento.", "error")

    return redirect(url_for("fornecedor.dashboard"))


@fluxo_bp.route("/rodada/<int:rodada_id>/lanchonete/<int:lanchonete_id>/entrega",
                methods=["POST"])
@login_required
@limiter.limit("60 per hour")
def informar_entrega(rodada_id, lanchonete_id):
    rodada, _fornecedor = _so_fornecedor_da_rodada(rodada_id)
    if not _fornecedor_atende_lanchonete(rodada_id, _fornecedor.id, lanchonete_id):
        abort(403)
    p = ParticipacaoRodada.query.filter_by(
        rodada_id=rodada_id, lanchonete_id=lanchonete_id,
    ).first_or_404()
    if not p.pagamento_confirmado_em:
        flash("Confirme o pagamento antes de informar a entrega.", "error")
        return redirect(url_for("fornecedor.dashboard"))

    data_str = request.form.get("entrega_data")
    try:
        entrega_dt = (datetime.strptime(data_str, "%Y-%m-%d").date()
                      if data_str else date.today())
    except ValueError:
        flash("Data de entrega inválida.", "error")
        return redirect(url_for("fornecedor.dashboard"))

    # Rejeita datas absurdas (digito errado ou ataque)
    hoje = date.today()
    if entrega_dt < hoje - timedelta(days=30) or entrega_dt > hoje + timedelta(days=365):
        flash("Data de entrega fora da janela aceitavel.", "error")
        return redirect(url_for("fornecedor.dashboard"))

    try:
        p.entrega_informada_em = _agora()
        p.entrega_informada_por_id = current_user.id
        p.entrega_data = entrega_dt
        _registrar_evento(rodada_id, EventoRodada.TIPO_ENTREGA_INFORMADA,
                          f"Fornecedor informou entrega para {entrega_dt.strftime('%d/%m/%Y')}",
                          lanchonete_id=lanchonete_id, ator_id=current_user.id)
        db.session.commit()

        lanch = db.session.get(Lanchonete, lanchonete_id)
        if lanch and lanch.responsavel:
            notificar_evento(
                lanch.responsavel,
                "Entrega informada",
                f"{_fornecedor.razao_social} informou entrega para "
                f"{entrega_dt.strftime('%d/%m/%Y')} na rodada '{rodada.nome}'. "
                f"Confirme o recebimento quando chegar.",
            )

        flash("Entrega registrada.", "success")
    except SQLAlchemyError:
        db.session.rollback()
        flash("Erro ao registrar entrega.", "error")

    return redirect(url_for("fornecedor.dashboard"))
