"""Rotas admin de Lanchonetes (listar, editar, export)."""
from flask import render_template, redirect, url_for, flash, request
from flask_login import login_required

from app import db
from app.models import Lanchonete
from app.services.csv_export import csv_response
from . import admin_bp, admin_required


@admin_bp.route("/lanchonetes")
@login_required
@admin_required
def lanchonetes():
    lista = Lanchonete.query.order_by(Lanchonete.nome_fantasia).all()
    return render_template("admin/lanchonetes.html", lanchonetes=lista)


@admin_bp.route("/lanchonetes/<int:lanchonete_id>/editar", methods=["GET", "POST"])
@login_required
@admin_required
def lanchonete_editar(lanchonete_id):
    lanchonete = Lanchonete.query.get_or_404(lanchonete_id)
    if request.method == "POST":
        lanchonete.nome_fantasia = request.form["nome_fantasia"].strip()
        lanchonete.cnpj = request.form.get("cnpj", "").strip() or None
        lanchonete.endereco = request.form.get("endereco", "").strip()
        lanchonete.bairro = request.form.get("bairro", "").strip()
        lanchonete.cidade = request.form.get("cidade", "").strip() or "Londrina"
        lanchonete.ativa = "ativa" in request.form
        db.session.commit()
        flash("Lanchonete atualizada!", "success")
        return redirect(url_for("admin.lanchonetes"))
    return render_template("admin/lanchonete_form.html", lanchonete=lanchonete)


@admin_bp.route("/lanchonetes/exportar.csv")
@login_required
@admin_required
def lanchonetes_exportar():
    lista = Lanchonete.query.order_by(Lanchonete.nome_fantasia).all()
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
