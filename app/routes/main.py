from flask import Blueprint, render_template, redirect, url_for
from flask_login import login_required, current_user
from sqlalchemy import func
from app import db
from app.models import Lanchonete, Rodada, ItemPedido, Cotacao, Produto

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def index():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))
    return render_template("index.html")


@main_bp.route("/dashboard")
@login_required
def dashboard():
    # Fornecedor vai para o painel dele
    if current_user.is_fornecedor:
        return redirect(url_for("fornecedor.dashboard"))

    # Admin
    if current_user.is_admin:
        total_lanchonetes = Lanchonete.query.filter_by(ativa=True).count()
        total_produtos = Produto.query.filter_by(ativo=True).count()
        rodada_aberta = Rodada.query.filter_by(status="aberta").first()

        pedidos_rodada = 0
        qtd_lanchonetes_rodada = 0
        if rodada_aberta:
            pedidos_rodada = ItemPedido.query.filter_by(rodada_id=rodada_aberta.id).count()
            qtd_lanchonetes_rodada = (
                db.session.query(func.count(func.distinct(ItemPedido.lanchonete_id)))
                .filter(ItemPedido.rodada_id == rodada_aberta.id)
                .scalar()
            )

        return render_template(
            "dashboard_admin.html",
            total_lanchonetes=total_lanchonetes,
            total_produtos=total_produtos,
            rodada_aberta=rodada_aberta,
            pedidos_rodada=pedidos_rodada,
            qtd_lanchonetes_rodada=qtd_lanchonetes_rodada,
        )

    # Lanchonete
    lanchonete = current_user.lanchonete
    rodada_aberta = Rodada.query.filter_by(status="aberta").first()

    meus_pedidos = []
    if rodada_aberta and lanchonete:
        meus_pedidos = (
            ItemPedido.query
            .filter_by(rodada_id=rodada_aberta.id, lanchonete_id=lanchonete.id)
            .all()
        )

    return render_template(
        "dashboard.html",
        lanchonete=lanchonete,
        rodada_aberta=rodada_aberta,
        meus_pedidos=meus_pedidos,
    )
