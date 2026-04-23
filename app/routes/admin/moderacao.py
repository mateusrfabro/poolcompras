"""Rotas admin de moderacao: pedidos de lanchonetes, produtos sugeridos e cotacoes finais."""
from datetime import datetime, timezone
from flask import render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from sqlalchemy.orm import joinedload

from app import db
from app.models import (
    Produto, Rodada, RodadaProduto, Cotacao,
    ItemPedido, ParticipacaoRodada, SubmissaoCotacao, NotaNegociacao,
)
from . import admin_bp, admin_required


@admin_bp.route("/rodadas/<int:rodada_id>/aprovar-produtos", methods=["GET", "POST"])
@login_required
@admin_required
def rodada_aprovar_produtos(rodada_id):
    """Admin aprova ou recusa produtos sugeridos pelos fornecedores."""
    rodada = db.get_or_404(Rodada, rodada_id)
    pendentes = (
        RodadaProduto.query
        .filter_by(rodada_id=rodada_id, aprovado=None)
        .filter(RodadaProduto.adicionado_por_fornecedor_id.isnot(None))
        .all()
    )

    if request.method == "POST":
        rp_id = request.form.get("rp_id", type=int)
        acao = request.form.get("acao")
        rp = db.session.get(RodadaProduto, rp_id)
        if not rp or rp.rodada_id != rodada_id:
            flash("Produto não encontrado.", "error")
            return redirect(url_for("admin.rodada_aprovar_produtos", rodada_id=rodada_id))

        if acao == "aprovar":
            rp.aprovado = True
            flash(f"Produto '{rp.produto.nome}' aprovado.", "success")
        elif acao == "recusar":
            rp.aprovado = False
            if rp.produto:
                rp.produto.ativo = False
            flash(f"Produto '{rp.produto.nome}' recusado.", "success")

        db.session.commit()
        return redirect(url_for("admin.rodada_aprovar_produtos", rodada_id=rodada_id))

    return render_template(
        "admin/rodada_aprovar_produtos.html",
        rodada=rodada,
        pendentes=pendentes,
    )


@admin_bp.route("/rodadas/<int:rodada_id>/moderar-pedidos", methods=["GET", "POST"])
@login_required
@admin_required
def moderar_pedidos(rodada_id):
    """Admin aprova/devolve/reprova pedidos enviados pelas lanchonetes."""
    rodada = db.get_or_404(Rodada, rodada_id)

    if request.method == "POST":
        participacao_id = request.form.get("participacao_id", type=int)
        acao = request.form.get("acao")
        motivo = request.form.get("motivo", "").strip() or None

        part = db.session.get(ParticipacaoRodada, participacao_id)
        if not part or part.rodada_id != rodada_id:
            flash("Participacao nao encontrada.", "error")
            return redirect(url_for("admin.moderar_pedidos", rodada_id=rodada_id))

        nome_lanchonete = part.lanchonete.nome_fantasia if part.lanchonete else f"#{part.lanchonete_id}"

        if acao == "aprovar":
            part.pedido_aprovado_em = datetime.now(timezone.utc).replace(tzinfo=None)
            part.pedido_aprovado_por_id = current_user.id
            part.pedido_devolvido_em = None
            part.pedido_reprovado_em = None
            flash(f"Pedido de {nome_lanchonete} aprovado.", "success")
        elif acao == "devolver":
            part.pedido_devolvido_em = datetime.now(timezone.utc).replace(tzinfo=None)
            part.pedido_motivo_devolucao = motivo
            part.pedido_enviado_em = None
            part.pedido_aprovado_em = None
            flash(f"Pedido de {nome_lanchonete} devolvido a lanchonete.", "success")
        elif acao == "reprovar":
            part.pedido_reprovado_em = datetime.now(timezone.utc).replace(tzinfo=None)
            part.pedido_aprovado_em = None
            flash(f"Pedido de {nome_lanchonete} reprovado.", "warning")
        elif acao == "reverter":
            part.pedido_aprovado_em = None
            part.pedido_aprovado_por_id = None
            flash(f"Aprovacao de {nome_lanchonete} revertida. Pedido voltou a aguardar moderacao.", "info")

        db.session.commit()
        return redirect(url_for("admin.moderar_pedidos", rodada_id=rodada_id))

    participacoes = (
        ParticipacaoRodada.query
        .options(joinedload(ParticipacaoRodada.lanchonete))
        .filter_by(rodada_id=rodada_id)
        .filter(ParticipacaoRodada.pedido_enviado_em.isnot(None))
        .all()
    )

    enviados = [p for p in participacoes
                if p.pedido_aprovado_em is None and p.pedido_reprovado_em is None]
    aprovados = [p for p in participacoes if p.pedido_aprovado_em is not None]
    reprovados = [p for p in participacoes if p.pedido_reprovado_em is not None]

    itens_por_participacao = {}
    for p in participacoes:
        itens_por_participacao[p.id] = (
            ItemPedido.query
            .options(joinedload(ItemPedido.produto))
            .filter_by(rodada_id=rodada_id, lanchonete_id=p.lanchonete_id)
            .all()
        )

    return render_template(
        "admin/moderar_pedidos.html",
        rodada=rodada,
        enviados=enviados,
        aprovados=aprovados,
        reprovados=reprovados,
        itens_por_participacao=itens_por_participacao,
    )


@admin_bp.route("/rodadas/<int:rodada_id>/aprovar-cotacoes", methods=["GET", "POST"])
@login_required
@admin_required
def aprovar_cotacoes(rodada_id):
    """Admin aprova/devolve cotacoes finais enviadas pelos fornecedores."""
    rodada = db.get_or_404(Rodada, rodada_id)

    if request.method == "POST":
        submissao_id = request.form.get("submissao_id", type=int)
        acao = request.form.get("acao")
        sub = db.session.get(SubmissaoCotacao, submissao_id)
        if not sub or sub.rodada_id != rodada_id:
            flash("Submissao nao encontrada.", "error")
            return redirect(url_for("admin.aprovar_cotacoes", rodada_id=rodada_id))

        nome_forn = sub.fornecedor.razao_social if sub.fornecedor else f"#{sub.fornecedor_id}"

        if acao == "aprovar":
            sub.aprovada_em = datetime.now(timezone.utc).replace(tzinfo=None)
            sub.aprovada_por_id = current_user.id
            sub.devolvida_em = None
            flash(f"Cotacao de {nome_forn} aprovada.", "success")
        elif acao == "devolver":
            sub.devolvida_em = datetime.now(timezone.utc).replace(tzinfo=None)
            sub.enviada_em = None
            sub.aprovada_em = None
            flash(f"Cotacao de {nome_forn} devolvida pra negociacao.", "success")
        elif acao == "reverter":
            sub.aprovada_em = None
            sub.aprovada_por_id = None
            flash(f"Aprovacao de {nome_forn} revertida.", "info")

        db.session.commit()
        return redirect(url_for("admin.aprovar_cotacoes", rodada_id=rodada_id))

    submissoes = (
        SubmissaoCotacao.query
        .options(joinedload(SubmissaoCotacao.fornecedor))
        .filter_by(rodada_id=rodada_id)
        .filter(SubmissaoCotacao.enviada_em.isnot(None))
        .all()
    )
    enviadas = [s for s in submissoes if s.aprovada_em is None]
    aprovadas = [s for s in submissoes if s.aprovada_em is not None]

    resumo_por_sub = {}
    notas_por_sub = {}
    for s in submissoes:
        cots = (
            db.session.query(Cotacao, Produto)
            .join(Produto, Cotacao.produto_id == Produto.id)
            .filter(Cotacao.rodada_id == rodada_id, Cotacao.fornecedor_id == s.fornecedor_id)
            .all()
        )
        resumo_por_sub[s.id] = cots
        notas_por_sub[s.id] = NotaNegociacao.query.filter_by(submissao_id=s.id)\
            .order_by(NotaNegociacao.criado_em.asc()).all()

    return render_template(
        "admin/aprovar_cotacoes.html",
        rodada=rodada,
        enviadas=enviadas,
        aprovadas=aprovadas,
        resumo_por_sub=resumo_por_sub,
        notas_por_sub=notas_por_sub,
    )


@admin_bp.route("/submissoes/<int:submissao_id>/nota", methods=["POST"])
@login_required
@admin_required
def adicionar_nota_negociacao_admin(submissao_id):
    sub = db.session.get(SubmissaoCotacao, submissao_id)
    if not sub:
        flash("Submissao nao encontrada.", "error")
        return redirect(url_for("main.dashboard"))
    texto = request.form.get("texto", "").strip()
    if not texto:
        flash("Escreva uma mensagem antes de enviar.", "warning")
        return redirect(url_for("admin.aprovar_cotacoes", rodada_id=sub.rodada_id))
    db.session.add(NotaNegociacao(
        submissao_id=sub.id,
        autor_tipo=NotaNegociacao.AUTOR_ADMIN,
        autor_usuario_id=current_user.id,
        texto=texto[:1000],
    ))
    db.session.commit()
    flash("Mensagem adicionada.", "success")
    return redirect(url_for("admin.aprovar_cotacoes", rodada_id=sub.rodada_id))
