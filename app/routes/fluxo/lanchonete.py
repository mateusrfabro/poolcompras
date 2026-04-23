"""Acoes da lanchonete no fluxo: aceitar/recusar proposta, enviar comprovante,
confirmar recebimento."""
from flask import request, redirect, url_for, flash
from flask_login import login_required, current_user
from sqlalchemy.exc import SQLAlchemyError

from app import db, limiter
from app.models import ParticipacaoRodada, EventoRodada
from app.services.storage import get_storage
from . import (
    fluxo_bp, COMPROVANTE_EXT, MAGIC_BYTES,
    _ja_aceita_fase_aceite, _agora, _obter_ou_criar_participacao,
    _registrar_evento, _notificar_fornecedores_comprovante, _so_dona_lanchonete,
)


@fluxo_bp.route("/rodada/<int:rodada_id>/aceitar", methods=["POST"])
@login_required
def aceitar_proposta(rodada_id):
    rodada, lanchonete = _so_dona_lanchonete(rodada_id)
    if not _ja_aceita_fase_aceite(rodada):
        flash("Rodada não está disponível para aceite.", "error")
        return redirect(url_for("historico.detalhe", rodada_id=rodada_id))

    try:
        p = _obter_ou_criar_participacao(rodada_id, lanchonete.id)
        if p.aceite_proposta is True:
            flash("Você já havia aceitado esta proposta.", "warning")
        else:
            p.aceite_proposta = True
            p.aceite_em = _agora()
            _registrar_evento(rodada_id, EventoRodada.TIPO_PROPOSTA_ACEITA,
                              "Cliente aceitou a proposta final",
                              lanchonete_id=lanchonete.id, ator_id=current_user.id)
            db.session.commit()
            flash("Proposta aceita! Próximo passo: enviar o comprovante de pagamento.", "success")
    except SQLAlchemyError:
        db.session.rollback()
        flash("Erro ao registrar aceite. Tente novamente.", "error")

    return redirect(url_for("historico.detalhe", rodada_id=rodada_id))


@fluxo_bp.route("/rodada/<int:rodada_id>/recusar", methods=["POST"])
@login_required
def recusar_proposta(rodada_id):
    rodada, lanchonete = _so_dona_lanchonete(rodada_id)
    if not _ja_aceita_fase_aceite(rodada):
        flash("Rodada não está disponível para recusa.", "error")
        return redirect(url_for("historico.detalhe", rodada_id=rodada_id))

    try:
        p = _obter_ou_criar_participacao(rodada_id, lanchonete.id)
        p.aceite_proposta = False
        p.aceite_em = _agora()
        _registrar_evento(rodada_id, EventoRodada.TIPO_PROPOSTA_RECUSADA,
                          "Cliente recusou a proposta final",
                          lanchonete_id=lanchonete.id, ator_id=current_user.id)
        db.session.commit()
        flash("Proposta recusada. Você ficou de fora desta rodada.", "success")
    except SQLAlchemyError:
        db.session.rollback()
        flash("Erro ao registrar recusa. Tente novamente.", "error")

    return redirect(url_for("historico.detalhe", rodada_id=rodada_id))


@fluxo_bp.route("/rodada/<int:rodada_id>/comprovante", methods=["POST"])
@login_required
@limiter.limit("20 per hour", error_message="Muitos uploads. Aguarde uma hora.")
def enviar_comprovante(rodada_id):
    rodada, lanchonete = _so_dona_lanchonete(rodada_id)
    p = ParticipacaoRodada.query.filter_by(
        rodada_id=rodada_id, lanchonete_id=lanchonete.id,
    ).first()
    if not p or p.aceite_proposta is not True:
        flash("Você precisa aceitar a proposta antes de enviar o comprovante.", "error")
        return redirect(url_for("historico.detalhe", rodada_id=rodada_id))

    arquivo = request.files.get("comprovante")
    if not arquivo or not arquivo.filename:
        flash("Selecione um arquivo para enviar.", "error")
        return redirect(url_for("historico.detalhe", rodada_id=rodada_id))

    ext = arquivo.filename.rsplit(".", 1)[-1].lower() if "." in arquivo.filename else ""
    if ext not in COMPROVANTE_EXT:
        flash("Formato não aceito. Envie PDF, JPG ou PNG.", "error")
        return redirect(url_for("historico.detalhe", rodada_id=rodada_id))

    # Valida magic bytes (defesa em profundidade — extensao pode ser falsificada)
    head = arquivo.stream.read(8)
    arquivo.stream.seek(0)
    tipo_real = next((t for prefixo, t in MAGIC_BYTES.items() if head.startswith(prefixo)), None)
    if not tipo_real:
        flash("Arquivo não parece ser um PDF/JPG/PNG válido.", "error")
        return redirect(url_for("historico.detalhe", rodada_id=rodada_id))

    try:
        storage = get_storage()
        if p.comprovante_key:
            storage.delete(p.comprovante_key)

        subdir = f"comprovantes/{rodada.data_abertura.strftime('%Y/%m')}"
        key = storage.save(arquivo, subdir=subdir, original_name=arquivo.filename)
        p.comprovante_key = key
        p.comprovante_em = _agora()
        _registrar_evento(rodada_id, EventoRodada.TIPO_COMPROVANTE_ENVIADO,
                          "Comprovante de pagamento enviado",
                          lanchonete_id=lanchonete.id, ator_id=current_user.id)
        db.session.commit()

        _notificar_fornecedores_comprovante(rodada, lanchonete)

        flash("Comprovante enviado! Aguardando confirmação do fornecedor.", "success")
    except SQLAlchemyError:
        db.session.rollback()
        flash("Erro ao salvar comprovante. Tente novamente.", "error")

    return redirect(url_for("historico.detalhe", rodada_id=rodada_id))


@fluxo_bp.route("/rodada/<int:rodada_id>/confirmar-recebimento", methods=["POST"])
@login_required
def confirmar_recebimento(rodada_id):
    rodada, lanchonete = _so_dona_lanchonete(rodada_id)
    p = ParticipacaoRodada.query.filter_by(
        rodada_id=rodada_id, lanchonete_id=lanchonete.id,
    ).first()
    if not p or not p.entrega_informada_em:
        flash("Fornecedor ainda não informou a entrega.", "error")
        return redirect(url_for("historico.detalhe", rodada_id=rodada_id))

    ok = request.form.get("status") == "ok"
    observacao = request.form.get("observacao", "").strip()[:500]

    try:
        p.recebimento_ok = ok
        p.recebimento_em = _agora()
        p.recebimento_observacao = observacao or None
        tipo = (EventoRodada.TIPO_RECEBIMENTO_CONFIRMADO if ok
                else EventoRodada.TIPO_RECEBIMENTO_PROBLEMA)
        desc = "Cliente confirmou recebimento OK" if ok else (observacao or "Problema no recebimento")
        _registrar_evento(rodada_id, tipo, desc,
                          lanchonete_id=lanchonete.id, ator_id=current_user.id)
        db.session.commit()
        flash("Recebimento registrado. Obrigado!", "success")
    except SQLAlchemyError:
        db.session.rollback()
        flash("Erro ao registrar recebimento.", "error")

    return redirect(url_for("historico.detalhe", rodada_id=rodada_id))
