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


# Campos sensiveis: mudanca exige reautenticacao com senha_atual.
# Redireciona fluxo de pagamento — sem reauth, sessao sequestrada pode
# redirecionar pagamentos pro atacante.
_CAMPOS_SENSIVEIS_FORNECEDOR = ("chave_pix", "banco", "agencia", "conta")
_CAMPOS_SENSIVEIS_LANCHONETE = ("cnpj",)


def _mudou(atual, novo_form):
    """True se novo_form (string) diferir do atual (str/None)."""
    atual_norm = (atual or "").strip()
    return atual_norm != novo_form.strip()


@perfil_bp.route("/", methods=["GET", "POST"])
@login_required
def editar():
    usuario = current_user

    if request.method == "POST":
        senha_atual = request.form.get("senha_atual", "")
        senha_nova = request.form.get("senha_nova", "")
        senha_conf = request.form.get("senha_confirmacao", "")
        # Troca de senha so dispara quando tem senha_nova/confirmacao — senha_atual
        # sozinha eh usada pra autorizar mudanca de campo sensivel sem trocar senha.
        vai_trocar_senha = bool(senha_nova or senha_conf)

        # --- Detectar mudanca em campos sensiveis ---
        mudou_sensivel = False
        if current_user.is_fornecedor and usuario.fornecedor:
            f = usuario.fornecedor
            for campo in _CAMPOS_SENSIVEIS_FORNECEDOR:
                if _mudou(getattr(f, campo), request.form.get(campo, "")):
                    mudou_sensivel = True
                    break
        if current_user.is_lanchonete and usuario.lanchonete:
            l = usuario.lanchonete
            for campo in _CAMPOS_SENSIVEIS_LANCHONETE:
                if _mudou(getattr(l, campo), request.form.get(campo, "")):
                    mudou_sensivel = True
                    break

        # Mudanca de senha OU de campo sensivel exige senha_atual correta.
        if vai_trocar_senha or mudou_sensivel:
            if not check_password_hash(usuario.senha_hash, senha_atual):
                if mudou_sensivel and not vai_trocar_senha:
                    flash("Informe sua senha atual para alterar dados bancários/CNPJ.", "error")
                else:
                    flash("Senha atual incorreta. Nada foi salvo.", "error")
                db.session.rollback()
                return redirect(url_for("perfil.editar"))

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

        # --- Troca de senha (se fluxo iniciado acima, senha_atual ja foi validada) ---
        if vai_trocar_senha:
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
