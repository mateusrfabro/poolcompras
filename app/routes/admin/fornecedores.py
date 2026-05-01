"""Rotas admin de Fornecedores (CRUD + export)."""
import logging
from flask import render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from sqlalchemy import select

from app import db
from app.models import Fornecedor
from app.services.csv_export import csv_response
from . import admin_bp, admin_required

logger = logging.getLogger(__name__)


@admin_bp.route("/fornecedores")
@login_required
@admin_required
def fornecedores():
    lista = db.session.scalars(select(Fornecedor).order_by(Fornecedor.razao_social)).all()
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
            chave_pix=request.form.get("chave_pix", "").strip() or None,
            banco=request.form.get("banco", "").strip() or None,
            agencia=request.form.get("agencia", "").strip() or None,
            conta=request.form.get("conta", "").strip() or None,
        )
        db.session.add(fornecedor)
        db.session.commit()
        # razao_social eh dado de negocio (CNPJ aberto) — log sem mask. Mas
        # email do responsavel (se houver) deve ser mascarado em logs futuros.
        logger.info(
            "ADMIN_FORNECEDOR_CRIADO admin=%s fornecedor=%s",
            current_user.id, fornecedor.id,
        )
        flash("Fornecedor cadastrado!", "success")
        return redirect(url_for("admin.fornecedores"))

    return render_template("admin/fornecedor_form.html", fornecedor=None)


@admin_bp.route("/fornecedores/<int:fornecedor_id>/editar", methods=["GET", "POST"])
@login_required
@admin_required
def fornecedor_editar(fornecedor_id):
    fornecedor = db.get_or_404(Fornecedor, fornecedor_id)
    if request.method == "POST":
        fornecedor.razao_social = request.form["razao_social"].strip()
        fornecedor.nome_contato = request.form.get("nome_contato", "").strip()
        fornecedor.telefone = request.form.get("telefone", "").strip()
        fornecedor.email = request.form.get("email", "").strip()
        fornecedor.cidade = request.form.get("cidade", "").strip()
        fornecedor.chave_pix = request.form.get("chave_pix", "").strip() or None
        fornecedor.banco = request.form.get("banco", "").strip() or None
        fornecedor.agencia = request.form.get("agencia", "").strip() or None
        fornecedor.conta = request.form.get("conta", "").strip() or None
        fornecedor.ativo = "ativo" in request.form
        # Invariante: Usuario.ativo segue Fornecedor.ativo (mesma logica da
        # rota lanchonete_editar). Fornecedor "desativado" nao deve logar.
        if fornecedor.responsavel:
            fornecedor.responsavel.ativo = fornecedor.ativo
        db.session.commit()
        flash("Fornecedor atualizado!", "success")
        return redirect(url_for("admin.fornecedores"))
    return render_template("admin/fornecedor_form.html", fornecedor=fornecedor)


@admin_bp.route("/fornecedores/exportar.csv")
@login_required
@admin_required
def fornecedores_exportar():
    fornecedores = db.session.scalars(select(Fornecedor).order_by(Fornecedor.razao_social)).all()
    logger.info("ADMIN_EXPORT_CSV admin=%s endpoint=fornecedores_exportar registros=%s",
                current_user.id, len(fornecedores))
    return csv_response(
        filename="fornecedores.csv",
        headers=["id", "razao_social", "nome_contato", "telefone", "email", "cidade", "ativo", "criado_em"],
        rows=[
            [f.id, f.razao_social, f.nome_contato or "", f.telefone or "",
             f.email or "", f.cidade or "", "sim" if f.ativo else "nao",
             f.criado_em.strftime("%Y-%m-%d %H:%M") if f.criado_em else ""]
            for f in fornecedores
        ],
    )
