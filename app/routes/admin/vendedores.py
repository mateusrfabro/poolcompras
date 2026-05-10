"""CRUD admin de Vendedores (SDR / comercial).

Listar, novo, editar, ativar/inativar. Cada vendedor eh 1-1 com Usuario
tipo='vendedor' — admin define email + senha inicial; vendedor troca
no primeiro login.
"""
import logging
import secrets
import string

from flask import render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from sqlalchemy import select

from app import db, limiter
from app.models import Usuario, Vendedor, AuditLog
from app.services.audit import audit
from app.services.passwords import hash_senha
from app.services.pii import mask_email
from . import admin_bp, admin_required

logger = logging.getLogger(__name__)


def _gerar_senha_temporaria(n: int = 10) -> str:
    """Senha aleatoria razoavel pra primeiro acesso (vendedor troca depois)."""
    alfabeto = string.ascii_letters + string.digits
    return "".join(secrets.choice(alfabeto) for _ in range(n))


@admin_bp.route("/vendedores")
@login_required
@admin_required
def vendedores():
    lista = db.session.scalars(
        select(Vendedor).order_by(Vendedor.nome)
    ).all()
    return render_template("admin/vendedores.html", vendedores=lista)


@admin_bp.route("/vendedores/novo", methods=["GET", "POST"])
@login_required
@admin_required
@limiter.limit("30 per hour", methods=["POST"],
               error_message="Muitos cadastros em sequencia. Aguarde 1 hora.")
def vendedor_novo():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        nome = request.form.get("nome", "").strip()
        meta = request.form.get("meta_mensal_clientes", "10").strip()

        if not email or not nome:
            flash("Email e nome são obrigatórios.", "error")
            return render_template("admin/vendedor_form.html",
                                   vendedor=None, form_data=request.form)
        try:
            meta_int = max(1, int(meta))
        except (ValueError, TypeError):
            meta_int = 10

        if db.session.execute(
            select(Usuario).where(Usuario.email == email)
        ).scalar_one_or_none():
            flash("Já existe um usuário com esse email.", "error")
            return render_template("admin/vendedor_form.html",
                                   vendedor=None, form_data=request.form)

        senha = _gerar_senha_temporaria()
        usuario = Usuario(
            email=email,
            senha_hash=hash_senha(senha),
            nome_responsavel=nome,
            telefone=request.form.get("telefone", "").strip(),
            tipo="vendedor",
            ativo=True,
        )
        db.session.add(usuario)
        db.session.flush()

        vendedor = Vendedor(
            usuario_id=usuario.id,
            nome=nome,
            meta_mensal_clientes=meta_int,
            ativo=True,
        )
        db.session.add(vendedor)
        db.session.commit()
        logger.info(
            "ADMIN_VENDEDOR_CRIADO admin=%s vendedor=%s email=%s",
            current_user.id, vendedor.id, mask_email(email),
        )
        audit(AuditLog.ACAO_VENDEDOR_CRIADO, recurso_tipo="vendedor",
              recurso_id=vendedor.id,
              detalhes=f"nome={nome[:80]} email={mask_email(email)}")
        # Senha temporaria fica no flash apenas pra o admin que criou —
        # nao persistimos em log/db. Admin copia e manda pro vendedor.
        flash(
            f"Vendedor '{nome}' criado. Login: {email} / Senha temporária: {senha} — "
            f"copie agora, ela não vai aparecer de novo.",
            "success",
        )
        return redirect(url_for("admin.vendedores"))

    return render_template("admin/vendedor_form.html",
                           vendedor=None, form_data={})


@admin_bp.route("/vendedores/<int:vendedor_id>/editar", methods=["GET", "POST"])
@login_required
@admin_required
def vendedor_editar(vendedor_id):
    vendedor = db.get_or_404(Vendedor, vendedor_id)
    if request.method == "POST":
        vendedor.nome = request.form.get("nome", "").strip() or vendedor.nome
        try:
            vendedor.meta_mensal_clientes = max(
                1, int(request.form.get("meta_mensal_clientes", "10"))
            )
        except (ValueError, TypeError):
            pass
        novo_status = "ativo" in request.form
        vendedor.ativo = novo_status
        # Invariante: Usuario.ativo segue Vendedor.ativo (vendedor inativo
        # nao deve logar — mesmo padrao de Lanchonete e Fornecedor).
        if vendedor.responsavel:
            vendedor.responsavel.ativo = novo_status
        db.session.commit()
        flash("Vendedor atualizado!", "success")
        return redirect(url_for("admin.vendedores"))
    return render_template("admin/vendedor_form.html", vendedor=vendedor)
