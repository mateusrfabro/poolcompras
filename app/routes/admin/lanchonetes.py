"""Rotas admin de Lanchonetes (listar, nova, editar, export)."""
import logging
from flask import render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from sqlalchemy import select
from app import db
from app.models import Lanchonete, Usuario
from app.services.passwords import hash_senha
from app.services.csv_export import csv_response
from . import admin_bp, admin_required

logger = logging.getLogger(__name__)


@admin_bp.route("/lanchonetes")
@login_required
@admin_required
def lanchonetes():
    lista = db.session.scalars(
        select(Lanchonete).order_by(Lanchonete.nome_fantasia)
    ).all()
    return render_template("admin/lanchonetes.html", lanchonetes=lista)


@admin_bp.route("/lanchonetes/nova", methods=["GET", "POST"])
@login_required
@admin_required
def lanchonete_nova():
    """Admin cadastra lanchonete + responsavel (Usuario) num unico form.

    Lanchonete.usuario_id e nullable=False, entao o Usuario eh obrigatorio.
    """
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        senha = request.form.get("senha", "")
        nome_responsavel = request.form.get("nome_responsavel", "").strip()

        # Validacoes minimas — as demais podem ser completadas depois pela propria lanchonete.
        # Passa dict de erros por campo pra template marcar com is-invalid.
        if not email or not senha or not nome_responsavel:
            flash("E-mail, senha e nome do responsavel sao obrigatorios.", "error")
            return render_template(
                "admin/lanchonete_form.html", lanchonete=None,
                form_data=request.form,
                erros={"email": not email, "senha": not senha,
                       "nome_responsavel": not nome_responsavel},
            )
        if len(senha) < 8:
            flash("Senha deve ter pelo menos 8 caracteres.", "error")
            return render_template(
                "admin/lanchonete_form.html", lanchonete=None,
                form_data=request.form,
                erros={"senha": "curta"},
            )
        if db.session.execute(
            select(Usuario).where(Usuario.email == email)
        ).scalar_one_or_none():
            flash("Ja existe um usuario com esse e-mail.", "error")
            return render_template(
                "admin/lanchonete_form.html", lanchonete=None,
                form_data=request.form,
                erros={"email": "duplicado"},
            )

        ativa = "ativa" in request.form
        usuario = Usuario(
            email=email,
            senha_hash=hash_senha(senha),
            nome_responsavel=nome_responsavel,
            telefone=request.form.get("telefone", "").strip(),
            tipo="lanchonete",
            ativo=ativa,  # alinha Usuario.ativo com Lanchonete.ativa (invariante)
        )
        db.session.add(usuario)
        db.session.flush()

        lanchonete = Lanchonete(
            usuario_id=usuario.id,
            nome_fantasia=request.form["nome_fantasia"].strip(),
            cnpj=request.form.get("cnpj", "").strip() or None,
            endereco=request.form.get("endereco", "").strip(),
            bairro=request.form.get("bairro", "").strip(),
            cidade=request.form.get("cidade", "").strip() or "Londrina",
            ativa=ativa,
        )
        db.session.add(lanchonete)
        db.session.commit()
        # Invalida KPI cacheado pra admin ver o numero novo na hora.
        cache.delete("kpi_total_lanchonetes")
        from app.routes.auth import _mask_email
        logger.info(
            "ADMIN_USUARIO_CRIADO admin=%s tipo=lanchonete usuario=%s email=%s",
            current_user.id, lanchonete.usuario_id, _mask_email(email),
        )
        flash(f"Lanchonete '{lanchonete.nome_fantasia}' cadastrada. Login: {email}", "success")
        return redirect(url_for("admin.lanchonetes"))

    return render_template("admin/lanchonete_form.html", lanchonete=None, form_data={})


@admin_bp.route("/lanchonetes/<int:lanchonete_id>/editar", methods=["GET", "POST"])
@login_required
@admin_required
def lanchonete_editar(lanchonete_id):
    lanchonete = db.get_or_404(Lanchonete, lanchonete_id)
    if request.method == "POST":
        lanchonete.nome_fantasia = request.form["nome_fantasia"].strip()
        lanchonete.cnpj = request.form.get("cnpj", "").strip() or None
        lanchonete.endereco = request.form.get("endereco", "").strip()
        lanchonete.bairro = request.form.get("bairro", "").strip()
        lanchonete.cidade = request.form.get("cidade", "").strip() or "Londrina"
        lanchonete.ativa = "ativa" in request.form
        # Invariante: Usuario.ativo segue Lanchonete.ativa. Sem isso, lanchonete
        # "desativada" no admin continua conseguindo logar e criar pedidos.
        if lanchonete.responsavel:
            lanchonete.responsavel.ativo = lanchonete.ativa
        db.session.commit()
        cache.delete("kpi_total_lanchonetes")  # ativa muda count
        flash("Lanchonete atualizada!", "success")
        return redirect(url_for("admin.lanchonetes"))
    return render_template("admin/lanchonete_form.html", lanchonete=lanchonete)


@admin_bp.route("/lanchonetes/exportar.csv")
@login_required
@admin_required
def lanchonetes_exportar():
    lista = db.session.scalars(
        select(Lanchonete).order_by(Lanchonete.nome_fantasia)
    ).all()
    logger.info("ADMIN_EXPORT_CSV admin=%s endpoint=lanchonetes_exportar registros=%s",
                current_user.id, len(lista))
    return csv_response(
        filename="lanchonetes.csv",
        headers=["id", "nome_fantasia", "responsavel", "email_responsavel",
                 "telefone", "cnpj", "endereco", "bairro", "cidade", "ativa", "criado_em"],
        rows=[
            [l.id, l.nome_fantasia,
             l.responsavel.nome_responsavel if l.responsavel else "",
             l.responsavel.email if l.responsavel else "",
             l.responsavel.telefone if l.responsavel else "",
             l.cnpj or "", l.endereco or "", l.bairro or "", l.cidade or "",
             "sim" if l.ativa else "nao",
             l.criado_em.strftime("%Y-%m-%d %H:%M") if l.criado_em else ""]
            for l in lista
        ],
    )
