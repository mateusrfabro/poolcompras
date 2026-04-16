"""
Acoes de transicao de estado no fluxo de uma rodada.

Cada acao:
1. Valida autorizacao (quem pode executar)
2. Valida pre-requisitos (fase anterior concluida, rodada em status compativel)
3. Atualiza ParticipacaoRodada
4. Gera EventoRodada correspondente (log imutavel)
5. Commit transacional; rollback em erro
"""
from datetime import datetime, timezone, date
from flask import Blueprint, request, redirect, url_for, flash, abort
from flask_login import login_required, current_user
from sqlalchemy.exc import SQLAlchemyError

from app import db
from app.models import (
    Rodada, ParticipacaoRodada, EventoRodada, Cotacao, Fornecedor,
)
from app.services.storage import get_storage

fluxo_bp = Blueprint("fluxo", __name__, url_prefix="/fluxo")


# Extensoes permitidas para comprovante + whitelist de magic bytes basica
COMPROVANTE_EXT = {"pdf", "jpg", "jpeg", "png"}
MAGIC_BYTES = {
    # PDF sempre comeca com %PDF-
    b"%PDF-": "pdf",
    # JPEG
    b"\xff\xd8\xff": "jpg",
    # PNG
    b"\x89PNG\r\n\x1a\n": "png",
}


def _ja_aceita_fase_aceite(rodada):
    """Rodada precisa estar finalizada para que haja proposta consolidada."""
    return rodada.status == "finalizada"


def _agora():
    return datetime.now(timezone.utc)


def _obter_ou_criar_participacao(rodada_id, lanchonete_id):
    p = ParticipacaoRodada.query.filter_by(
        rodada_id=rodada_id, lanchonete_id=lanchonete_id,
    ).first()
    if not p:
        p = ParticipacaoRodada(rodada_id=rodada_id, lanchonete_id=lanchonete_id)
        db.session.add(p)
        db.session.flush()
    return p


def _registrar_evento(rodada_id, tipo, descricao, lanchonete_id=None, ator_id=None):
    db.session.add(EventoRodada(
        rodada_id=rodada_id,
        lanchonete_id=lanchonete_id,
        ator_id=ator_id,
        tipo=tipo,
        descricao=descricao,
    ))


def _so_dona_lanchonete(rodada_id):
    """Garante que current_user e a dona da lanchonete participante. Retorna (rodada, lanchonete)."""
    if not current_user.is_lanchonete or not current_user.lanchonete:
        abort(403)
    rodada = Rodada.query.get_or_404(rodada_id)
    return rodada, current_user.lanchonete


def _so_fornecedor_da_rodada(rodada_id):
    """Garante que current_user e fornecedor que cotou nessa rodada."""
    if not current_user.is_fornecedor or not current_user.fornecedor:
        abort(403)
    rodada = Rodada.query.get_or_404(rodada_id)
    cotou = Cotacao.query.filter_by(
        rodada_id=rodada_id, fornecedor_id=current_user.fornecedor.id,
    ).first()
    if not cotou:
        abort(403)
    return rodada, current_user.fornecedor


# ---------- Acoes da lanchonete ----------

@fluxo_bp.route("/rodada/<int:rodada_id>/aceitar", methods=["POST"])
@login_required
def aceitar_proposta(rodada_id):
    rodada, lanchonete = _so_dona_lanchonete(rodada_id)
    if not _ja_aceita_fase_aceite(rodada):
        flash("Rodada nao esta disponivel para aceite.", "error")
        return redirect(url_for("historico.detalhe", rodada_id=rodada_id))

    try:
        p = _obter_ou_criar_participacao(rodada_id, lanchonete.id)
        if p.aceite_proposta is True:
            flash("Voce ja havia aceitado esta proposta.", "warning")
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
        flash("Rodada nao esta disponivel para recusa.", "error")
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
def enviar_comprovante(rodada_id):
    rodada, lanchonete = _so_dona_lanchonete(rodada_id)
    p = ParticipacaoRodada.query.filter_by(
        rodada_id=rodada_id, lanchonete_id=lanchonete.id,
    ).first()
    if not p or p.aceite_proposta is not True:
        flash("Voce precisa aceitar a proposta antes de enviar o comprovante.", "error")
        return redirect(url_for("historico.detalhe", rodada_id=rodada_id))

    arquivo = request.files.get("comprovante")
    if not arquivo or not arquivo.filename:
        flash("Selecione um arquivo para enviar.", "error")
        return redirect(url_for("historico.detalhe", rodada_id=rodada_id))

    # Valida extensao
    ext = arquivo.filename.rsplit(".", 1)[-1].lower() if "." in arquivo.filename else ""
    if ext not in COMPROVANTE_EXT:
        flash("Formato nao aceito. Envie PDF, JPG ou PNG.", "error")
        return redirect(url_for("historico.detalhe", rodada_id=rodada_id))

    # Valida magic bytes (defesa em profundidade — extensao pode ser falsificada)
    head = arquivo.stream.read(8)
    arquivo.stream.seek(0)
    tipo_real = next((t for prefixo, t in MAGIC_BYTES.items() if head.startswith(prefixo)), None)
    if not tipo_real:
        flash("Arquivo nao parece ser PDF/JPG/PNG valido.", "error")
        return redirect(url_for("historico.detalhe", rodada_id=rodada_id))

    try:
        storage = get_storage()
        # Substitui comprovante anterior se houver
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
        flash("Comprovante enviado! Aguardando confirmacao do fornecedor.", "success")
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
        flash("Fornecedor ainda nao informou a entrega.", "error")
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


# ---------- Acoes do fornecedor ----------

@fluxo_bp.route("/rodada/<int:rodada_id>/lanchonete/<int:lanchonete_id>/pagamento",
                methods=["POST"])
@login_required
def confirmar_pagamento(rodada_id, lanchonete_id):
    rodada, _fornecedor = _so_fornecedor_da_rodada(rodada_id)
    p = ParticipacaoRodada.query.filter_by(
        rodada_id=rodada_id, lanchonete_id=lanchonete_id,
    ).first_or_404()
    if not p.comprovante_key:
        flash("Cliente ainda nao enviou o comprovante.", "error")
        return redirect(url_for("fornecedor.dashboard"))
    if p.pagamento_confirmado_em:
        flash("Pagamento ja foi confirmado anteriormente.", "warning")
        return redirect(url_for("fornecedor.dashboard"))

    try:
        p.pagamento_confirmado_em = _agora()
        p.pagamento_confirmado_por_id = current_user.id
        _registrar_evento(rodada_id, EventoRodada.TIPO_PAGAMENTO_CONFIRMADO,
                          "Fornecedor confirmou recebimento do pagamento",
                          lanchonete_id=lanchonete_id, ator_id=current_user.id)
        db.session.commit()
        flash("Pagamento confirmado.", "success")
    except SQLAlchemyError:
        db.session.rollback()
        flash("Erro ao confirmar pagamento.", "error")

    return redirect(url_for("fornecedor.dashboard"))


@fluxo_bp.route("/rodada/<int:rodada_id>/lanchonete/<int:lanchonete_id>/entrega",
                methods=["POST"])
@login_required
def informar_entrega(rodada_id, lanchonete_id):
    rodada, _fornecedor = _so_fornecedor_da_rodada(rodada_id)
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
        flash("Data de entrega invalida.", "error")
        return redirect(url_for("fornecedor.dashboard"))

    try:
        p.entrega_informada_em = _agora()
        p.entrega_informada_por_id = current_user.id
        p.entrega_data = entrega_dt
        _registrar_evento(rodada_id, EventoRodada.TIPO_ENTREGA_INFORMADA,
                          f"Fornecedor informou entrega para {entrega_dt.strftime('%d/%m/%Y')}",
                          lanchonete_id=lanchonete_id, ator_id=current_user.id)
        db.session.commit()
        flash("Entrega registrada.", "success")
    except SQLAlchemyError:
        db.session.rollback()
        flash("Erro ao registrar entrega.", "error")

    return redirect(url_for("fornecedor.dashboard"))
