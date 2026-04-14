from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from sqlalchemy import func
from app import db
from app.models import Rodada, ItemPedido, Cotacao, Produto

fornecedor_bp = Blueprint("fornecedor", __name__, url_prefix="/fornecedor")


def fornecedor_required(f):
    from functools import wraps

    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_fornecedor:
            flash("Acesso restrito a fornecedores.", "error")
            return redirect(url_for("main.dashboard"))
        return f(*args, **kwargs)

    return decorated


@fornecedor_bp.route("/dashboard")
@login_required
@fornecedor_required
def dashboard():
    fornecedor = current_user.fornecedor

    # Rodadas com status "fechada" (prontas para cotação)
    rodadas_para_cotar = Rodada.query.filter(
        Rodada.status.in_(["fechada", "cotando"])
    ).order_by(Rodada.data_fechamento.desc()).all()

    # Cotações já enviadas por este fornecedor
    minhas_cotacoes = (
        Cotacao.query
        .filter_by(fornecedor_id=fornecedor.id)
        .order_by(Cotacao.criado_em.desc())
        .limit(20)
        .all()
    ) if fornecedor else []

    return render_template(
        "fornecedor/dashboard.html",
        fornecedor=fornecedor,
        rodadas_para_cotar=rodadas_para_cotar,
        minhas_cotacoes=minhas_cotacoes,
    )


@fornecedor_bp.route("/rodada/<int:rodada_id>")
@login_required
@fornecedor_required
def ver_demanda(rodada_id):
    rodada = Rodada.query.get_or_404(rodada_id)

    # Demanda agregada — sem mostrar quais lanchonetes pediram
    agregado = (
        db.session.query(
            Produto.id,
            Produto.nome,
            Produto.categoria,
            Produto.unidade,
            func.sum(ItemPedido.quantidade).label("total_quantidade"),
        )
        .join(ItemPedido, ItemPedido.produto_id == Produto.id)
        .filter(ItemPedido.rodada_id == rodada_id)
        .group_by(Produto.id, Produto.nome, Produto.categoria, Produto.unidade)
        .order_by(Produto.categoria, Produto.nome)
        .all()
    )

    # Cotações já enviadas por mim nesta rodada
    fornecedor = current_user.fornecedor
    minhas = []
    if fornecedor:
        minhas = Cotacao.query.filter_by(
            rodada_id=rodada_id, fornecedor_id=fornecedor.id
        ).all()

    return render_template(
        "fornecedor/demanda.html",
        rodada=rodada,
        agregado=agregado,
        minhas_cotacoes=minhas,
    )


@fornecedor_bp.route("/rodada/<int:rodada_id>/cotar", methods=["GET", "POST"])
@login_required
@fornecedor_required
def enviar_cotacao(rodada_id):
    rodada = Rodada.query.get_or_404(rodada_id)
    fornecedor = current_user.fornecedor

    if rodada.status not in ("fechada", "cotando"):
        flash("Esta rodada não está aberta para cotações.", "warning")
        return redirect(url_for("fornecedor.dashboard"))

    # Produtos com demanda nesta rodada
    produtos_ids = (
        db.session.query(func.distinct(ItemPedido.produto_id))
        .filter(ItemPedido.rodada_id == rodada_id)
        .all()
    )
    produtos_ids = [p[0] for p in produtos_ids]
    produtos = Produto.query.filter(Produto.id.in_(produtos_ids)).order_by(Produto.categoria, Produto.nome).all()

    # Quantidades agregadas
    qtds = dict(
        db.session.query(
            ItemPedido.produto_id,
            func.sum(ItemPedido.quantidade),
        )
        .filter(ItemPedido.rodada_id == rodada_id)
        .group_by(ItemPedido.produto_id)
        .all()
    )

    if request.method == "POST":
        count = 0
        for produto in produtos:
            preco = request.form.get(f"preco_{produto.id}", type=float)
            if preco and preco > 0:
                # Atualiza se já existe, senão cria
                existente = Cotacao.query.filter_by(
                    rodada_id=rodada_id,
                    fornecedor_id=fornecedor.id,
                    produto_id=produto.id,
                ).first()

                if existente:
                    existente.preco_unitario = preco
                else:
                    cotacao = Cotacao(
                        rodada_id=rodada_id,
                        fornecedor_id=fornecedor.id,
                        produto_id=produto.id,
                        preco_unitario=preco,
                    )
                    db.session.add(cotacao)
                count += 1

        if rodada.status == "fechada":
            rodada.status = "cotando"

        db.session.commit()
        flash(f"Cotação enviada! {count} produto(s) cotado(s).", "success")
        return redirect(url_for("fornecedor.ver_demanda", rodada_id=rodada_id))

    return render_template(
        "fornecedor/cotar.html",
        rodada=rodada,
        produtos=produtos,
        qtds=qtds,
    )