"""Edicao de perfil: o proprio usuario corrige seus dados cadastrais + senha.

Regras:
- Email eh readonly (troca de e-mail eh feature separada por nao ser trivial)
- CNPJ da lanchonete: editavel (erros de cadastro precisam ser corrigidos por ela)
- Troca de senha eh opcional: se senha_nova vazia, nao altera
- Troca de senha exige senha_atual correta (protege de sessao sequestrada)
"""
from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from werkzeug.security import check_password_hash, generate_password_hash

from app import db

perfil_bp = Blueprint("perfil", __name__, url_prefix="/perfil")


@perfil_bp.route("/", methods=["GET", "POST"])
@login_required
def editar():
    usuario = current_user

    if request.method == "POST":
        # --- Dados do Usuario (comum aos 3 tipos) ---
        usuario.nome_responsavel = request.form.get("nome_responsavel", "").strip() or usuario.nome_responsavel
        usuario.telefone = request.form.get("telefone", "").strip()

        # --- Dados especificos por tipo ---
        if current_user.is_lanchonete and usuario.lanchonete:
            l = usuario.lanchonete
            l.nome_fantasia = request.form.get("nome_fantasia", "").strip() or l.nome_fantasia
            l.cnpj = request.form.get("cnpj", "").strip() or None
            l.endereco = request.form.get("endereco", "").strip()
            l.bairro = request.form.get("bairro", "").strip()
            l.cidade = request.form.get("cidade", "").strip() or "Londrina"
        elif current_user.is_fornecedor and usuario.fornecedor:
            f = usuario.fornecedor
            f.razao_social = request.form.get("razao_social", "").strip() or f.razao_social
            f.nome_contato = request.form.get("nome_contato", "").strip()
            f.telefone = request.form.get("telefone_fornecedor", "").strip() or usuario.telefone
            f.cidade = request.form.get("cidade", "").strip()
            f.chave_pix = request.form.get("chave_pix", "").strip() or None
            f.banco = request.form.get("banco", "").strip() or None
            f.agencia = request.form.get("agencia", "").strip() or None
            f.conta = request.form.get("conta", "").strip() or None

        # --- Troca de senha (opcional) ---
        senha_atual = request.form.get("senha_atual", "")
        senha_nova = request.form.get("senha_nova", "")
        senha_conf = request.form.get("senha_confirmacao", "")

        if senha_nova or senha_conf or senha_atual:
            if not check_password_hash(usuario.senha_hash, senha_atual):
                flash("Senha atual incorreta. Demais dados não foram salvos.", "error")
                db.session.rollback()
                return redirect(url_for("perfil.editar"))
            if len(senha_nova) < 8:
                flash("A nova senha deve ter pelo menos 8 caracteres.", "error")
                db.session.rollback()
                return redirect(url_for("perfil.editar"))
            if senha_nova != senha_conf:
                flash("As senhas não conferem.", "error")
                db.session.rollback()
                return redirect(url_for("perfil.editar"))
            usuario.senha_hash = generate_password_hash(senha_nova)
            flash("Perfil atualizado e senha trocada com sucesso.", "success")
        else:
            flash("Perfil atualizado com sucesso.", "success")

        db.session.commit()
        return redirect(url_for("perfil.editar"))

    return render_template("perfil/editar.html", usuario=usuario)
