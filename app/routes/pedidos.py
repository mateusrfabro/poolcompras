from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from app import db
from app.models import Produto, Rodada, ItemPedido

pedidos_bp = Blueprint("pedidos", __name__, url_prefix="/pedidos")


@pedidos_bp.route("/")
@login_required
def listar():
    lanchonete = current_user.lanchonete
    if not lanchonete:
        flash("Complete seu cadastro primeiro.", "error")
        return redirect(url_for("main.dashboard"))

    rodada_aberta = Rodada.query.filter_by(status="aberta").first()
    meus_pedidos = []
    if rodada_aberta:
        meus_pedidos = (
            ItemPedido.query
            .filter_by(rodada_id=rodada_aberta.id, lanchonete_id=lanchonete.id)
            .all()
        )

    return render_template(
        "pedidos/listar.html",
        rodada=rodada_aberta,
        pedidos=meus_pedidos,
    )


@pedidos_bp.route("/novo", methods=["GET", "POST"])
@login_required
def novo():
    lanchonete = current_user.lanchonete
    rodada_aberta = Rodada.query.filter_by(status="aberta").first()

    if not rodada_aberta:
        flash("Nenhuma rodada aberta no momento.", "warning")
        return redirect(url_for("pedidos.listar"))

    if request.method == "POST":
        produto_id = request.form.get("produto_id", type=int)
        quantidade = request.form.get("quantidade", type=float)
        observacao = request.form.get("observacao", "").strip()

        if not produto_id or not quantidade or quantidade <= 0:
            flash("Selecione um produto e informe a quantidade.", "error")
        else:
            existente = ItemPedido.query.filter_by(
                rodada_id=rodada_aberta.id,
                lanchonete_id=lanchonete.id,
                produto_id=produto_id,
            ).first()

            if existente:
                existente.quantidade += quantidade
                if observacao:
                    existente.observacao = observacao
                flash("Quantidade atualizada no pedido existente.", "success")
            else:
                item = ItemPedido(
                    rodada_id=rodada_aberta.id,
                    lanchonete_id=lanchonete.id,
                    produto_id=produto_id,
                    quantidade=quantidade,
                    observacao=observacao,
                )
                db.session.add(item)
                flash("Pedido adicionado!", "success")

            db.session.commit()
            return redirect(url_for("pedidos.listar"))

    produtos = Produto.query.filter_by(ativo=True).order_by(Produto.categoria, Produto.nome).all()
    return render_template(
        "pedidos/novo.html",
        rodada=rodada_aberta,
        produtos=produtos,
    )


@pedidos_bp.route("/remover/<int:item_id>", methods=["POST"])
@login_required
def remover(item_id):
    item = ItemPedido.query.get_or_404(item_id)
    lanchonete = current_user.lanchonete

    if item.lanchonete_id != lanchonete.id:
        flash("Você não pode remover este item.", "error")
        return redirect(url_for("pedidos.listar"))

    if item.rodada.status != "aberta":
        flash("Esta rodada já foi fechada.", "error")
        return redirect(url_for("pedidos.listar"))

    db.session.delete(item)
    db.session.commit()
    flash("Item removido do pedido.", "success")
    return redirect(url_for("pedidos.listar"))
