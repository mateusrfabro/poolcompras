from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from app import db
from app.models import Usuario, Lanchonete, Fornecedor

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        senha = request.form.get("senha", "")

        usuario = Usuario.query.filter_by(email=email).first()
        if usuario and check_password_hash(usuario.senha_hash, senha):
            login_user(usuario)
            next_page = request.args.get("next")
            return redirect(next_page or url_for("main.dashboard"))

        flash("E-mail ou senha incorretos.", "error")

    return render_template("auth/login.html")


@auth_bp.route("/registro", methods=["GET", "POST"])
def registro():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        senha = request.form.get("senha", "")
        nome = request.form.get("nome_responsavel", "").strip()
        telefone = request.form.get("telefone", "").strip()
        nome_fantasia = request.form.get("nome_fantasia", "").strip()
        cnpj = request.form.get("cnpj", "").strip()
        endereco = request.form.get("endereco", "").strip()
        bairro = request.form.get("bairro", "").strip()

        if Usuario.query.filter_by(email=email).first():
            flash("Este e-mail já está cadastrado.", "error")
            return render_template("auth/registro.html")

        usuario = Usuario(
            email=email,
            senha_hash=generate_password_hash(senha),
            nome_responsavel=nome,
            telefone=telefone,
            tipo="lanchonete",
        )
        db.session.add(usuario)
        db.session.flush()

        lanchonete = Lanchonete(
            usuario_id=usuario.id,
            nome_fantasia=nome_fantasia,
            cnpj=cnpj if cnpj else None,
            endereco=endereco,
            bairro=bairro,
        )
        db.session.add(lanchonete)
        db.session.commit()

        login_user(usuario)
        flash("Cadastro realizado! Bem-vindo ao PoolCompras.", "success")
        return redirect(url_for("main.dashboard"))

    return render_template("auth/registro.html")


@auth_bp.route("/registro/fornecedor", methods=["GET", "POST"])
def registro_fornecedor():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        senha = request.form.get("senha", "")
        nome = request.form.get("nome_responsavel", "").strip()
        telefone = request.form.get("telefone", "").strip()
        razao_social = request.form.get("razao_social", "").strip()
        cidade = request.form.get("cidade", "").strip()

        if Usuario.query.filter_by(email=email).first():
            flash("Este e-mail já está cadastrado.", "error")
            return render_template("auth/registro_fornecedor.html")

        usuario = Usuario(
            email=email,
            senha_hash=generate_password_hash(senha),
            nome_responsavel=nome,
            telefone=telefone,
            tipo="fornecedor",
        )
        db.session.add(usuario)
        db.session.flush()

        fornecedor = Fornecedor(
            usuario_id=usuario.id,
            razao_social=razao_social,
            nome_contato=nome,
            telefone=telefone,
            email=email,
            cidade=cidade,
        )
        db.session.add(fornecedor)
        db.session.commit()

        login_user(usuario)
        flash("Cadastro realizado! Bem-vindo ao PoolCompras.", "success")
        return redirect(url_for("fornecedor.dashboard"))

    return render_template("auth/registro_fornecedor.html")


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("auth.login"))
