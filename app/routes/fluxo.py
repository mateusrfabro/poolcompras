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

from app import db, limiter
from app.models import (
    Rodada, ParticipacaoRodada, EventoRodada, Cotacao, Fornecedor,
    AvaliacaoRodada, SubmissaoCotacao, Lanchonete,
)
from app.services.storage import get_storage
from app.services.notificacoes import notificar_evento

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
    """Rodada aceita aceite quando:
    - status == 'finalizada' (fluxo antigo — admin fechou a rodada), OU
    - status == 'em_negociacao' com ao menos 1 SubmissaoCotacao aprovada
      (fluxo novo — lanchonetes ja podem aceitar proposta parcial)
    """
    if rodada.status == "finalizada":
        return True
    if rodada.status == "em_negociacao":
        return db.session.query(SubmissaoCotacao.id).filter_by(
            rodada_id=rodada.id
        ).filter(SubmissaoCotacao.aprovada_em.isnot(None)).first() is not None
    return False


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


def _notificar_fornecedores_comprovante(rodada, lanchonete):
    """Notifica fornecedores vencedores que a lanchonete X enviou comprovante."""
    from app.models import ItemPedido
    # Fornecedores distintos que venceram algum item dessa lanchonete nessa rodada
    forn_ids = {
        fid for (fid,) in db.session.query(Cotacao.fornecedor_id)
            .join(ItemPedido,
                  (ItemPedido.rodada_id == Cotacao.rodada_id) &
                  (ItemPedido.produto_id == Cotacao.produto_id))
            .filter(Cotacao.rodada_id == rodada.id,
                    Cotacao.selecionada.is_(True),
                    ItemPedido.lanchonete_id == lanchonete.id)
            .distinct().all()
    }
    if not forn_ids:
        return
    for f in Fornecedor.query.filter(Fornecedor.id.in_(forn_ids)).all():
        if f.responsavel:
            notificar_evento(
                f.responsavel,
                "Comprovante recebido",
                f"{lanchonete.nome_fantasia} enviou o comprovante de pagamento "
                f"da rodada '{rodada.nome}'. Confirme o recebimento quando "
                f"conciliar o valor na conta.",
            )


def _so_dona_lanchonete(rodada_id):
    """Garante que current_user e a dona da lanchonete participante. Retorna (rodada, lanchonete)."""
    if not current_user.is_lanchonete or not current_user.lanchonete:
        abort(403)
    rodada = db.get_or_404(Rodada, rodada_id)
    return rodada, current_user.lanchonete


def _so_fornecedor_da_rodada(rodada_id):
    """Garante que current_user e fornecedor que cotou nessa rodada."""
    if not current_user.is_fornecedor or not current_user.fornecedor:
        abort(403)
    rodada = db.get_or_404(Rodada, rodada_id)
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

    # Valida extensao
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

        # Notifica fornecedores vencedores dos itens dessa lanchonete
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


# ---------- Avaliacao (opcao D: nota geral; se <=3, detalha por fornecedor) ----------

@fluxo_bp.route("/rodada/<int:rodada_id>/avaliar", methods=["POST"])
@login_required
def avaliar(rodada_id):
    """Nota geral da rodada (1-5).
    Se >= 4: replica para todos os fornecedores da rodada automaticamente.
    Se <= 3: redireciona para tela de detalhe por fornecedor.
    """
    rodada, lanchonete = _so_dona_lanchonete(rodada_id)
    p = ParticipacaoRodada.query.filter_by(
        rodada_id=rodada_id, lanchonete_id=lanchonete.id,
    ).first_or_404()
    if p.recebimento_ok is None:
        flash("Confirme o recebimento antes de avaliar.", "error")
        return redirect(url_for("historico.detalhe", rodada_id=rodada_id))

    try:
        nota = int(request.form.get("estrelas", "0"))
    except ValueError:
        nota = 0
    if nota < 1 or nota > 5:
        flash("Informe uma nota entre 1 e 5 estrelas.", "error")
        return redirect(url_for("historico.detalhe", rodada_id=rodada_id))

    try:
        p.avaliacao_geral = nota
        p.avaliacao_em = _agora()

        if nota >= 4:
            # Opcao D caminho rapido: replica para todos fornecedores da rodada
            fornecedores_ids = [
                fid for (fid,) in db.session.query(Cotacao.fornecedor_id)
                    .filter_by(rodada_id=rodada_id).distinct().all()
            ]
            for fid in fornecedores_ids:
                existe = AvaliacaoRodada.query.filter_by(
                    rodada_id=rodada_id, lanchonete_id=lanchonete.id, fornecedor_id=fid,
                ).first()
                if not existe:
                    db.session.add(AvaliacaoRodada(
                        rodada_id=rodada_id, lanchonete_id=lanchonete.id,
                        fornecedor_id=fid, estrelas=nota,
                    ))

            _registrar_evento(rodada_id, EventoRodada.TIPO_AVALIACAO_ENVIADA,
                              f"Cliente avaliou com {nota} estrelas",
                              lanchonete_id=lanchonete.id, ator_id=current_user.id)
            db.session.commit()
            flash(f"Obrigado pela avaliacao de {nota} estrelas!", "success")
            return redirect(url_for("historico.detalhe", rodada_id=rodada_id))

        # nota <= 3: salva parcial (para tracking) e vai pro detalhe
        db.session.commit()
        return redirect(url_for("fluxo.avaliar_detalhado", rodada_id=rodada_id))

    except SQLAlchemyError:
        db.session.rollback()
        flash("Erro ao salvar avaliação.", "error")
        return redirect(url_for("historico.detalhe", rodada_id=rodada_id))


@fluxo_bp.route("/rodada/<int:rodada_id>/avaliar-detalhado",
                methods=["GET", "POST"])
@login_required
def avaliar_detalhado(rodada_id):
    """Tela de detalhe: nota por fornecedor quando a geral foi baixa (<=3)."""
    from flask import render_template
    rodada, lanchonete = _so_dona_lanchonete(rodada_id)
    p = ParticipacaoRodada.query.filter_by(
        rodada_id=rodada_id, lanchonete_id=lanchonete.id,
    ).first_or_404()

    # Fornecedores que cotaram nesta rodada
    forn_ids = [fid for (fid,) in db.session.query(Cotacao.fornecedor_id)
                    .filter_by(rodada_id=rodada_id).distinct().all()]
    fornecedores = Fornecedor.query.filter(Fornecedor.id.in_(forn_ids)).all()

    if request.method == "POST":
        try:
            for forn in fornecedores:
                nota_str = request.form.get(f"estrelas_{forn.id}")
                coment = request.form.get(f"comentario_{forn.id}", "").strip()[:500] or None
                try:
                    nota = int(nota_str) if nota_str else None
                except ValueError:
                    nota = None
                if not nota or nota < 1 or nota > 5:
                    continue
                existe = AvaliacaoRodada.query.filter_by(
                    rodada_id=rodada_id, lanchonete_id=lanchonete.id,
                    fornecedor_id=forn.id,
                ).first()
                if existe:
                    existe.estrelas = nota
                    existe.comentario = coment
                else:
                    db.session.add(AvaliacaoRodada(
                        rodada_id=rodada_id, lanchonete_id=lanchonete.id,
                        fornecedor_id=forn.id, estrelas=nota, comentario=coment,
                    ))

            _registrar_evento(rodada_id, EventoRodada.TIPO_AVALIACAO_ENVIADA,
                              f"Cliente detalhou avaliacao (geral: {p.avaliacao_geral} estrelas)",
                              lanchonete_id=lanchonete.id, ator_id=current_user.id)
            db.session.commit()
            flash("Avaliação detalhada registrada. Obrigado pelo feedback!", "success")
            return redirect(url_for("historico.detalhe", rodada_id=rodada_id))
        except SQLAlchemyError:
            db.session.rollback()
            flash("Erro ao salvar avaliacoes.", "error")

    return render_template("fluxo/avaliar_detalhado.html",
                           rodada=rodada, participacao=p, fornecedores=fornecedores)


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

        # Notifica a lanchonete dona da participacao
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
        flash("Data de entrega inválida.", "error")
        return redirect(url_for("fornecedor.dashboard"))

    # Rejeita datas absurdas (digito errado ou ataque)
    hoje = date.today()
    from datetime import timedelta
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
