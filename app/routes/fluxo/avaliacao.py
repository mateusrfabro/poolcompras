"""Acoes de avaliacao no fluxo (opcao D: nota geral; se <=3, detalha por fornecedor)."""
from flask import request, redirect, url_for, flash, render_template
from flask_login import login_required, current_user
from sqlalchemy.exc import SQLAlchemyError

from app import db
from app.models import (
    ParticipacaoRodada, EventoRodada, Cotacao, Fornecedor, AvaliacaoRodada,
)
from . import fluxo_bp, _agora, _registrar_evento, _so_dona_lanchonete


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
    rodada, lanchonete = _so_dona_lanchonete(rodada_id)
    p = ParticipacaoRodada.query.filter_by(
        rodada_id=rodada_id, lanchonete_id=lanchonete.id,
    ).first_or_404()

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
