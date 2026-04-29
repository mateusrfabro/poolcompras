"""Rotas admin de moderacao: pedidos de lanchonetes, produtos sugeridos e cotacoes finais."""
import logging
from datetime import datetime, timezone
from flask import render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from sqlalchemy.orm import joinedload

from app import db, limiter
from app.models import (
    Produto, Rodada, RodadaProduto, Cotacao,
    ItemPedido, ParticipacaoRodada, SubmissaoCotacao, NotaNegociacao,
)
from app.services.notificacoes import (
    notificar_evento, notificar_lanchonetes_cotacao_aprovada,
)
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

        notif_titulo = notif_detalhes = None
        if acao == "aprovar":
            # Idempotencia: 2 cliques rapidos / 2 admins simultaneos nao geram 2 notifs.
            if part.pedido_aprovado_em is not None:
                flash(f"Pedido de {nome_lanchonete} ja estava aprovado.", "info")
                return redirect(url_for("admin.moderar_pedidos", rodada_id=rodada_id))
            part.pedido_aprovado_em = datetime.now(timezone.utc)
            part.pedido_aprovado_por_id = current_user.id
            part.pedido_devolvido_em = None
            part.pedido_reprovado_em = None
            flash(f"Pedido de {nome_lanchonete} aprovado.", "success")
            notif_titulo = "Pedido aprovado"
            notif_detalhes = (f"Seu pedido na rodada '{rodada.nome}' foi aprovado "
                              f"e entrou no pool.")
        elif acao == "devolver":
            # Idempotencia: ja devolvida e lanchonete nao reenviou ainda — nao
            # duplica notif/log. Se lanchonete reenviou (pedido_enviado_em
            # != None), eh OK devolver de novo.
            if part.pedido_devolvido_em is not None and part.pedido_enviado_em is None:
                flash(f"Pedido de {nome_lanchonete} ja estava devolvido e aguardando reenvio.", "info")
                return redirect(url_for("admin.moderar_pedidos", rodada_id=rodada_id))
            part.pedido_devolvido_em = datetime.now(timezone.utc)
            part.pedido_motivo_devolucao = motivo
            part.pedido_enviado_em = None
            part.pedido_aprovado_em = None
            flash(f"Pedido de {nome_lanchonete} devolvido a lanchonete.", "success")
            notif_titulo = "Pedido devolvido"
            motivo_txt = f" Motivo: {motivo}." if motivo else ""
            notif_detalhes = (f"Seu pedido na rodada '{rodada.nome}' foi devolvido "
                              f"pelo admin.{motivo_txt} Ajuste e reenvie.")
        elif acao == "reprovar":
            # Reprovar eh estado terminal — 2 cliques nao devem duplicar log/notif.
            if part.pedido_reprovado_em is not None:
                flash(f"Pedido de {nome_lanchonete} ja estava reprovado.", "info")
                return redirect(url_for("admin.moderar_pedidos", rodada_id=rodada_id))
            part.pedido_reprovado_em = datetime.now(timezone.utc)
            part.pedido_aprovado_em = None
            flash(f"Pedido de {nome_lanchonete} reprovado.", "warning")
            notif_titulo = "Pedido reprovado"
            notif_detalhes = (f"Seu pedido na rodada '{rodada.nome}' foi reprovado "
                              f"pelo admin. Contate-nos se precisar.")
        elif acao == "reverter":
            # Sem aprovacao em vigor, nao ha o que reverter.
            if part.pedido_aprovado_em is None:
                flash(f"Pedido de {nome_lanchonete} nao esta aprovado — nada a reverter.", "info")
                return redirect(url_for("admin.moderar_pedidos", rodada_id=rodada_id))
            part.pedido_aprovado_em = None
            part.pedido_aprovado_por_id = None
            flash(f"Aprovacao de {nome_lanchonete} revertida. Pedido voltou a aguardar moderacao.", "info")

        db.session.commit()
        logger.info(
            "ADMIN_MODERAR_PEDIDO admin=%s acao=%s rodada=%s lanchonete=%s",
            current_user.id, acao, rodada_id, part.lanchonete_id,
        )

        # Notifica a lanchonete do desfecho
        if notif_titulo and part.lanchonete and part.lanchonete.responsavel:
            notificar_evento(part.lanchonete.responsavel, notif_titulo, notif_detalhes)

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

        notif_titulo = notif_detalhes = None
        if acao == "aprovar":
            # Guarda idempotente: 2 admins clicando "Aprovar" simultaneo nao
            # devem disparar 2 notificacoes nem 2 logs. Se ja foi aprovada,
            # mensagem amigavel e retorna sem mutacao.
            if sub.aprovada_em is not None:
                flash(f"Cotacao de {nome_forn} ja estava aprovada.", "info")
                return redirect(url_for("admin.aprovar_cotacoes", rodada_id=rodada_id))
            sub.aprovada_em = datetime.now(timezone.utc)
            sub.aprovada_por_id = current_user.id
            sub.devolvida_em = None
            flash(f"Cotacao de {nome_forn} aprovada.", "success")
            notif_titulo = "Cotação aprovada"
            notif_detalhes = (f"Sua cotação final na rodada '{rodada.nome}' foi "
                              f"aprovada pelo admin e está disponível pras lanchonetes.")
        elif acao == "devolver":
            # Idempotencia: ja devolvida e fornecedor ainda nao reenviou.
            if sub.devolvida_em is not None and sub.enviada_em is None:
                flash(f"Cotacao de {nome_forn} ja estava devolvida e aguardando reenvio.", "info")
                return redirect(url_for("admin.aprovar_cotacoes", rodada_id=rodada_id))
            sub.devolvida_em = datetime.now(timezone.utc)
            sub.enviada_em = None
            sub.aprovada_em = None
            flash(f"Cotacao de {nome_forn} devolvida pra negociacao.", "success")
            notif_titulo = "Cotação devolvida"
            notif_detalhes = (f"Sua cotação na rodada '{rodada.nome}' foi devolvida "
                              f"pelo admin. Ajuste os preços e reenvie.")
        elif acao == "reverter":
            # Sem aprovacao em vigor, nada a reverter.
            if sub.aprovada_em is None:
                flash(f"Cotacao de {nome_forn} nao esta aprovada — nada a reverter.", "info")
                return redirect(url_for("admin.aprovar_cotacoes", rodada_id=rodada_id))
            sub.aprovada_em = None
            sub.aprovada_por_id = None
            flash(f"Aprovacao de {nome_forn} revertida.", "info")

        db.session.commit()
        logger.info(
            "ADMIN_APROVAR_COTACAO admin=%s acao=%s rodada=%s submissao=%s fornecedor=%s",
            current_user.id, acao, rodada_id, submissao_id, sub.fornecedor_id,
        )

        if notif_titulo and sub.fornecedor and sub.fornecedor.responsavel:
            notificar_evento(sub.fornecedor.responsavel, notif_titulo, notif_detalhes)
        # Aprovacao tambem deve avisar lanchonetes que tem proposta nova
        # disponivel pra aceitar (notif separada — ja que a notif de
        # "Cotacao aprovada" eh do ponto de vista do fornecedor).
        if acao == "aprovar" and sub.fornecedor:
            notificar_lanchonetes_cotacao_aprovada(rodada, sub.fornecedor)
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
