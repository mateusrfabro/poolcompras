from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from datetime import datetime
from app import db
from app.models import Produto, Rodada, Fornecedor, Lanchonete

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


def admin_required(f):
    from functools import wraps

    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_admin:
            flash("Acesso restrito a administradores.", "error")
            return redirect(url_for("main.dashboard"))
        return f(*args, **kwargs)

    return decorated


# --- Produtos ---
@admin_bp.route("/produtos")
@login_required
@admin_required
def produtos():
    lista = Produto.query.order_by(Produto.categoria, Produto.nome).all()
    return render_template("admin/produtos.html", produtos=lista)


@admin_bp.route("/produtos/novo", methods=["GET", "POST"])
@login_required
@admin_required
def produto_novo():
    if request.method == "POST":
        produto = Produto(
            nome=request.form["nome"].strip(),
            descricao=request.form.get("descricao", "").strip(),
            categoria=request.form["categoria"].strip(),
            unidade=request.form["unidade"].strip(),
        )
        db.session.add(produto)
        db.session.commit()
        flash("Produto cadastrado!", "success")
        return redirect(url_for("admin.produtos"))

    return render_template("admin/produto_form.html", produto=None)


@admin_bp.route("/produtos/<int:produto_id>/editar", methods=["GET", "POST"])
@login_required
@admin_required
def produto_editar(produto_id):
    produto = Produto.query.get_or_404(produto_id)

    if request.method == "POST":
        produto.nome = request.form["nome"].strip()
        produto.descricao = request.form.get("descricao", "").strip()
        produto.categoria = request.form["categoria"].strip()
        produto.unidade = request.form["unidade"].strip()
        produto.ativo = "ativo" in request.form
        db.session.commit()
        flash("Produto atualizado!", "success")
        return redirect(url_for("admin.produtos"))

    return render_template("admin/produto_form.html", produto=produto)


# --- Fornecedores ---
@admin_bp.route("/fornecedores")
@login_required
@admin_required
def fornecedores():
    lista = Fornecedor.query.order_by(Fornecedor.razao_social).all()
    return render_template("admin/fornecedores.html", fornecedores=lista)


@admin_bp.route("/fornecedores/novo", methods=["GET", "POST"])
@login_required
@admin_required
def fornecedor_novo():
    if request.method == "POST":
        fornecedor = Fornecedor(
            razao_social=request.form["razao_social"].strip(),
            nome_contato=request.form.get("nome_contato", "").strip(),
            telefone=request.form.get("telefone", "").strip(),
            email=request.form.get("email", "").strip(),
            cidade=request.form.get("cidade", "").strip(),
        )
        db.session.add(fornecedor)
        db.session.commit()
        flash("Fornecedor cadastrado!", "success")
        return redirect(url_for("admin.fornecedores"))

    return render_template("admin/fornecedor_form.html", fornecedor=None)


# --- Rodadas ---
@admin_bp.route("/rodadas/nova", methods=["GET", "POST"])
@login_required
@admin_required
def rodada_nova():
    if request.method == "POST":
        rodada = Rodada(
            nome=request.form["nome"].strip(),
            data_abertura=datetime.strptime(request.form["data_abertura"], "%Y-%m-%d"),
            data_fechamento=datetime.strptime(request.form["data_fechamento"], "%Y-%m-%d"),
        )
        db.session.add(rodada)
        db.session.commit()
        flash("Rodada criada!", "success")
        return redirect(url_for("rodadas.listar"))

    return render_template("admin/rodada_form.html")


@admin_bp.route("/rodadas/<int:rodada_id>/fechar", methods=["POST"])
@login_required
@admin_required
def rodada_fechar(rodada_id):
    rodada = Rodada.query.get_or_404(rodada_id)
    rodada.status = "fechada"
    db.session.commit()
    flash(f"Rodada '{rodada.nome}' fechada. Hora de cotar!", "success")
    return redirect(url_for("rodadas.detalhe", rodada_id=rodada_id))


# --- Lanchonetes ---
@admin_bp.route("/lanchonetes")
@login_required
@admin_required
def lanchonetes():
    lista = Lanchonete.query.order_by(Lanchonete.nome_fantasia).all()
    return render_template("admin/lanchonetes.html", lanchonetes=lista)
