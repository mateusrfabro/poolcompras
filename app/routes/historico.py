"""
Historico de rodadas da lanchonete logada.
Lista as rodadas em que a lanchonete participou (com status e contagem
de produtos). Detalhe expandido fica em template separado.
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from sqlalchemy import func
from app import db
from app.models import (
    Rodada, ItemPedido, Cotacao, Produto, Lanchonete, Fornecedor,
)

historico_bp = Blueprint("historico", __name__, url_prefix="/minhas-rodadas")


# Status que aparecem na aba Historico (nao queremos mostrar so "aberta" aqui)
STATUS_HISTORICO = ("finalizada", "cancelada", "fechada", "cotando")


@historico_bp.route("/")
@login_required
def listar():
    """Listagem de rodadas em que a lanchonete logada participou."""
    if current_user.is_admin or current_user.is_fornecedor:
        flash("Esta area e apenas para lanchonetes.", "warning")
        return redirect(url_for("main.dashboard"))

    lanchonete = current_user.lanchonete
    if not lanchonete:
        flash("Complete seu cadastro primeiro.", "error")
        return redirect(url_for("main.dashboard"))

    # Filtro de status (default: todas)
    filtro_status = request.args.get("status", "todas")

    # Subquery: rodadas em que essa lanchonete teve pedidos
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

    if filtro_status == "todas":
        # Mostra todas em que ela participou (inclui aberta tambem)
        pass
    elif filtro_status in STATUS_HISTORICO:
        rodadas_q = rodadas_q.filter(Rodada.status == filtro_status)
    elif filtro_status == "aberta":
        rodadas_q = rodadas_q.filter(Rodada.status == "aberta")

    rodadas = rodadas_q.all()

    # Conta totais p/ filtros (badges)
    contagem = dict(
        db.session.query(Rodada.status, func.count(Rodada.id))
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
    )


@historico_bp.route("/<int:rodada_id>")
@login_required
def detalhe(rodada_id):
    """Detalhe expandido de uma rodada da lanchonete logada."""
    if current_user.is_admin or current_user.is_fornecedor:
        flash("Esta area e apenas para lanchonetes.", "warning")
        return redirect(url_for("main.dashboard"))

    lanchonete = current_user.lanchonete
    if not lanchonete:
        flash("Complete seu cadastro primeiro.", "error")
        return redirect(url_for("main.dashboard"))

    rodada = Rodada.query.get_or_404(rodada_id)

    # Garante que a lanchonete participou desta rodada
    participou = (
        ItemPedido.query
        .filter_by(rodada_id=rodada_id, lanchonete_id=lanchonete.id)
        .first()
    )
    if not participou:
        flash("Voce nao participou desta rodada.", "warning")
        return redirect(url_for("historico.listar"))

    # Itens da lanchonete nesta rodada (com produto)
    meus_itens = (
        ItemPedido.query
        .filter_by(rodada_id=rodada_id, lanchonete_id=lanchonete.id)
        .join(Produto, ItemPedido.produto_id == Produto.id)
        .order_by(Produto.categoria, Produto.nome)
        .all()
    )

    # Para cada item: preco de partida (mais alto) e preco final (mais baixo / vencedor)
    # Estrategia simples antes da Fase 2: olha cotacoes da rodada.
    itens_detalhe = []
    for item in meus_itens:
        cotacoes_produto = (
            Cotacao.query
            .filter_by(rodada_id=rodada_id, produto_id=item.produto_id)
            .all()
        )
        if cotacoes_produto:
            preco_partida = max(c.preco_unitario for c in cotacoes_produto)
            preco_final = min(c.preco_unitario for c in cotacoes_produto)
            forn_vencedor = next(
                (c.fornecedor for c in cotacoes_produto if c.selecionada),
                None,
            )
        else:
            preco_partida = preco_final = None
            forn_vencedor = None

        itens_detalhe.append({
            "item": item,
            "produto": item.produto,
            "quantidade": item.quantidade,
            "preco_partida": preco_partida,
            "preco_final": preco_final,
            "fornecedor": forn_vencedor,
            "subtotal": (preco_final * item.quantidade) if preco_final else None,
        })

    total_estimado = sum(i["subtotal"] for i in itens_detalhe if i["subtotal"])
    total_partida = sum(
        (i["preco_partida"] or 0) * i["quantidade"] for i in itens_detalhe
    )
    economia = total_partida - total_estimado if total_partida and total_estimado else 0

    return render_template(
        "historico/detalhe.html",
        rodada=rodada,
        lanchonete=lanchonete,
        itens=itens_detalhe,
        total_estimado=total_estimado,
        total_partida=total_partida,
        economia=economia,
    )