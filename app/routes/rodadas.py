from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from datetime import datetime
from sqlalchemy import func
from app import db
from app.models import Rodada, ItemPedido, Cotacao, Fornecedor, Produto, ParticipacaoRodada, RodadaProduto, SubmissaoCotacao

rodadas_bp = Blueprint("rodadas", __name__, url_prefix="/rodadas")


@rodadas_bp.route("/")
@login_required
def listar():
    rodadas = Rodada.query.order_by(Rodada.data_abertura.desc()).all()
    return render_template("rodadas/listar.html", rodadas=rodadas)


@rodadas_bp.route("/<int:rodada_id>")
@login_required
def detalhe(rodada_id):
    rodada = Rodada.query.get_or_404(rodada_id)

    # Pool unificado: SOMENTE pedidos aprovados pelo admin
    # (pendentes/rascunho/devolvidos/reprovados nao entram no agregado da rodada)
    agregado = (
        db.session.query(
            Produto.id,
            Produto.nome,
            Produto.categoria,
            Produto.unidade,
            func.sum(ItemPedido.quantidade).label("total_quantidade"),
            func.count(func.distinct(ItemPedido.lanchonete_id)).label("total_lanchonetes"),
        )
        .join(ItemPedido, ItemPedido.produto_id == Produto.id)
        .join(ParticipacaoRodada,
              (ParticipacaoRodada.rodada_id == ItemPedido.rodada_id) &
              (ParticipacaoRodada.lanchonete_id == ItemPedido.lanchonete_id))
        .filter(ItemPedido.rodada_id == rodada_id)
        .filter(ParticipacaoRodada.pedido_aprovado_em.isnot(None))
        .group_by(Produto.id, Produto.nome, Produto.categoria, Produto.unidade)
        .order_by(Produto.categoria, Produto.nome)
        .all()
    )

    cotacoes = Cotacao.query.filter_by(rodada_id=rodada_id).all()

    # Produtos sugeridos aguardando aprovacao (admin)
    pendentes_aprovacao = 0
    pedidos_pendentes_moderacao = 0
    cotacoes_pendentes_aprovacao = 0
    if current_user.is_admin:
        pendentes_aprovacao = (
            RodadaProduto.query
            .filter_by(rodada_id=rodada_id, aprovado=None)
            .filter(RodadaProduto.adicionado_por_fornecedor_id.isnot(None))
            .count()
        )
        pedidos_pendentes_moderacao = (
            ParticipacaoRodada.query
            .filter_by(rodada_id=rodada_id)
            .filter(ParticipacaoRodada.pedido_enviado_em.isnot(None))
            .filter(ParticipacaoRodada.pedido_aprovado_em.is_(None))
            .filter(ParticipacaoRodada.pedido_reprovado_em.is_(None))
            .count()
        )
        cotacoes_pendentes_aprovacao = (
            SubmissaoCotacao.query
            .filter_by(rodada_id=rodada_id)
            .filter(SubmissaoCotacao.enviada_em.isnot(None))
            .filter(SubmissaoCotacao.aprovada_em.is_(None))
            .count()
        )

    # Se lanchonete logada: mostra "Seu pedido" ao lado do total agregado
    meus_pedidos_map = {}
    if current_user.is_lanchonete and current_user.lanchonete:
        meus = (
            ItemPedido.query
            .filter_by(rodada_id=rodada_id, lanchonete_id=current_user.lanchonete.id)
            .all()
        )
        meus_pedidos_map = {m.produto_id: m.quantidade for m in meus}

    # Enriquecer agregado com preco_partida + melhor cotacao + fornecedor + subtotal
    # (so considera cotacoes de submissoes APROVADAS pelo admin)
    partidas_por_produto = {
        rp.produto_id: float(rp.preco_partida) if rp.preco_partida else None
        for rp in RodadaProduto.query.filter_by(rodada_id=rodada_id).all()
    }
    submissoes_aprovadas_ids = {
        s.fornecedor_id for s in SubmissaoCotacao.query
        .filter_by(rodada_id=rodada_id)
        .filter(SubmissaoCotacao.aprovada_em.isnot(None)).all()
    }
    # Cotacoes elegiveis: so de submissoes aprovadas (ou todas se nao houver fluxo novo em uso)
    from sqlalchemy.orm import joinedload as _jl
    cotacoes_full = (
        Cotacao.query.options(_jl(Cotacao.fornecedor))
        .filter_by(rodada_id=rodada_id).all()
    )
    melhor_por_produto = {}
    for c in cotacoes_full:
        if submissoes_aprovadas_ids and c.fornecedor_id not in submissoes_aprovadas_ids:
            continue
        atual = melhor_por_produto.get(c.produto_id)
        if atual is None or c.preco_unitario < atual.preco_unitario:
            melhor_por_produto[c.produto_id] = c

    agregado_enriquecido = []
    for item in agregado:
        melhor = melhor_por_produto.get(item.id)
        preco_final = float(melhor.preco_unitario) if melhor else None
        forn = melhor.fornecedor if melhor else None
        subtotal = (preco_final * float(item.total_quantidade)) if preco_final else None
        agregado_enriquecido.append({
            "id": item.id,
            "nome": item.nome,
            "categoria": item.categoria,
            "unidade": item.unidade,
            "total_quantidade": item.total_quantidade,
            "total_lanchonetes": item.total_lanchonetes,
            "preco_partida": partidas_por_produto.get(item.id),
            "preco_final": preco_final,
            "fornecedor": forn,
            "subtotal": subtotal,
        })

    # Status das submissoes (visivel a todos perfis)
    submissoes_todas = (
        SubmissaoCotacao.query.options(_jl(SubmissaoCotacao.fornecedor))
        .filter_by(rodada_id=rodada_id).all()
    )

    return render_template(
        "rodadas/detalhe.html",
        rodada=rodada,
        agregado=agregado_enriquecido,
        cotacoes=cotacoes,
        meus_pedidos_map=meus_pedidos_map,
        pendentes_aprovacao=pendentes_aprovacao,
        pedidos_pendentes_moderacao=pedidos_pendentes_moderacao,
        cotacoes_pendentes_aprovacao=cotacoes_pendentes_aprovacao,
        submissoes_status=submissoes_todas,
    )


@rodadas_bp.route("/<int:rodada_id>/cotar", methods=["GET", "POST"])
@login_required
def cotar(rodada_id):
    if not current_user.is_admin:
        flash("Apenas administradores podem inserir cotações.", "error")
        return redirect(url_for("rodadas.detalhe", rodada_id=rodada_id))

    rodada = Rodada.query.get_or_404(rodada_id)
    fornecedores = Fornecedor.query.filter_by(ativo=True).all()

    produtos_ids = (
        db.session.query(func.distinct(ItemPedido.produto_id))
        .filter(ItemPedido.rodada_id == rodada_id)
        .all()
    )
    produtos_ids = [p[0] for p in produtos_ids]
    produtos = Produto.query.filter(Produto.id.in_(produtos_ids)).all()

    if request.method == "POST":
        fornecedor_id = request.form.get("fornecedor_id", type=int)
        for produto in produtos:
            preco = request.form.get(f"preco_{produto.id}", type=float)
            if preco and preco > 0:
                cotacao = Cotacao(
                    rodada_id=rodada_id,
                    fornecedor_id=fornecedor_id,
                    produto_id=produto.id,
                    preco_unitario=preco,
                )
                db.session.add(cotacao)

        db.session.commit()
        flash("Cotação registrada!", "success")
        return redirect(url_for("rodadas.detalhe", rodada_id=rodada_id))

    return render_template(
        "rodadas/cotar.html",
        rodada=rodada,
        fornecedores=fornecedores,
        produtos=produtos,
    )
