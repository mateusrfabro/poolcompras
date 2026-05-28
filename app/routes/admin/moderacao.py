"""Rotas admin de moderacao: pedidos de lanchonetes, produtos sugeridos e cotacoes finais.

Logica de aprovar/devolver/reprovar/reverter foi extraida pra:
    app/services/moderacao_pedido.py   (4 acoes em pedido)
    app/services/moderacao_cotacao.py  (3 acoes em cotacao final)
"""
import logging
from flask import render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from sqlalchemy.orm import joinedload

from app import db, limiter
from app.models import (
    Produto, Rodada, RodadaProduto, Cotacao,
    ItemPedido, ParticipacaoRodada, SubmissaoCotacao, NotaNegociacao,
)
from app.services import moderacao_pedido, moderacao_cotacao
from . import admin_bp, admin_required

logger = logging.getLogger(__name__)


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
            # Idempotencia: ja decidido (aprovado True ou False), nada a fazer.
            if rp.aprovado is not None:
                flash(f"Produto '{rp.produto.nome}' ja foi decidido nesta rodada.", "info")
                return redirect(url_for("admin.rodada_aprovar_produtos", rodada_id=rodada_id))
            rp.aprovado = True
            # Produto sugerido nasce inativo; aprovacao libera no catalogo global.
            if rp.produto and not rp.produto.ativo:
                rp.produto.ativo = True
            flash(f"Produto '{rp.produto.nome}' aprovado.", "success")
        elif acao == "recusar":
            if rp.aprovado is not None:
                flash(f"Produto '{rp.produto.nome}' ja foi decidido nesta rodada.", "info")
                return redirect(url_for("admin.rodada_aprovar_produtos", rodada_id=rodada_id))
            # Apenas marca a SUGESTAO como recusada nesta rodada.
            # Antes: tambem setava produto.ativo=False — side effect GLOBAL que
            # desativava o produto em todas as outras rodadas (bug latente).
            rp.aprovado = False
            flash(f"Produto '{rp.produto.nome}' recusado nesta rodada.", "success")

        db.session.commit()
        logger.info(
            "ADMIN_APROVAR_PRODUTO admin=%s acao=%s rodada=%s rp=%s produto=%s",
            current_user.id, acao, rodada_id, rp_id,
            rp.produto_id if rp.produto else None,
        )
        return redirect(url_for("admin.rodada_aprovar_produtos", rodada_id=rodada_id))

    return render_template(
        "admin/rodada_aprovar_produtos.html",
        rodada=rodada,
        pendentes=pendentes,
    )


# Dispatch acao -> service. Cada handler tem assinatura unificada
# (part, admin, rodada) exceto devolver(part, admin, rodada, motivo).
_ACOES_PEDIDO = {
    "aprovar":  lambda part, admin, rodada, motivo: moderacao_pedido.aprovar(part, admin, rodada),
    "devolver": lambda part, admin, rodada, motivo: moderacao_pedido.devolver(part, admin, rodada, motivo),
    "reprovar": lambda part, admin, rodada, motivo: moderacao_pedido.reprovar(part, admin, rodada),
    "reverter": lambda part, admin, rodada, motivo: moderacao_pedido.reverter(part, admin, rodada),
}


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
            flash("Participação não encontrada.", "error")
            return redirect(url_for("admin.moderar_pedidos", rodada_id=rodada_id))

        handler = _ACOES_PEDIDO.get(acao)
        if handler is None:
            flash("Ação inválida.", "error")
            return redirect(url_for("admin.moderar_pedidos", rodada_id=rodada_id))

        result = handler(part, current_user, rodada, motivo)
        flash(result.flash_msg, result.flash_tipo)
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

    # 1 query agrupada em vez de N (1 por lanchonete). Evita N+1 com 50+ lanchonetes.
    lanchonete_ids = [p.lanchonete_id for p in participacoes]
    itens_por_participacao = {p.id: [] for p in participacoes}
    if lanchonete_ids:
        itens_all = (
            ItemPedido.query
            .options(joinedload(ItemPedido.produto))
            .filter(ItemPedido.rodada_id == rodada_id)
            .filter(ItemPedido.lanchonete_id.in_(lanchonete_ids))
            .all()
        )
        part_by_lanch = {p.lanchonete_id: p.id for p in participacoes}
        for item in itens_all:
            pid = part_by_lanch.get(item.lanchonete_id)
            if pid is not None:
                itens_por_participacao[pid].append(item)

    return render_template(
        "admin/moderar_pedidos.html",
        rodada=rodada,
        enviados=enviados,
        aprovados=aprovados,
        reprovados=reprovados,
        itens_por_participacao=itens_por_participacao,
    )


_ACOES_COTACAO = {
    "aprovar":  moderacao_cotacao.aprovar,
    "devolver": moderacao_cotacao.devolver,
    "reverter": moderacao_cotacao.reverter,
}


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
            flash("Submissão não encontrada.", "error")
            return redirect(url_for("admin.aprovar_cotacoes", rodada_id=rodada_id))

        handler = _ACOES_COTACAO.get(acao)
        if handler is None:
            flash("Ação inválida.", "error")
            return redirect(url_for("admin.aprovar_cotacoes", rodada_id=rodada_id))

        result = handler(sub, current_user, rodada)
        flash(result.flash_msg, result.flash_tipo)
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

    # Batch: 1 query pra todas cotacoes + 1 query pra todas notas (evita N+1)
    forn_ids = [s.fornecedor_id for s in submissoes]
    sub_ids = [s.id for s in submissoes]

    resumo_por_sub = {s.id: [] for s in submissoes}
    if forn_ids:
        todas_cots = (
            db.session.query(Cotacao, Produto)
            .join(Produto, Cotacao.produto_id == Produto.id)
            .filter(Cotacao.rodada_id == rodada_id,
                    Cotacao.fornecedor_id.in_(forn_ids))
            .all()
        )
        forn_to_sub = {s.fornecedor_id: s.id for s in submissoes}
        for c, p in todas_cots:
            sub_id = forn_to_sub.get(c.fornecedor_id)
            if sub_id is not None:
                resumo_por_sub[sub_id].append((c, p))

    notas_por_sub = {s.id: [] for s in submissoes}
    if sub_ids:
        todas_notas = (
            NotaNegociacao.query
            .filter(NotaNegociacao.submissao_id.in_(sub_ids))
            .order_by(NotaNegociacao.criado_em.asc())
            .all()
        )
        for n in todas_notas:
            notas_por_sub[n.submissao_id].append(n)

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
@limiter.limit("30/hour")
def adicionar_nota_negociacao_admin(submissao_id):
    sub = db.session.get(SubmissaoCotacao, submissao_id)
    if not sub:
        flash("Submissão não encontrada.", "error")
        return redirect(url_for("main.dashboard"))
    # Simetria com fornecedor.cotacao_final.adicionar_nota_negociacao: chat
    # eh append-only ate aprovacao. Apos aprovada, nao ha mais negociacao.
    if sub.aprovada_em:
        flash("Cotação já foi aprovada — sem negociação ativa.", "warning")
        return redirect(url_for("admin.aprovar_cotacoes", rodada_id=sub.rodada_id))
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
