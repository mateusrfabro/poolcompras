"""Visao admin: tabela de comissao de todos os fornecedores."""
import logging

from flask import render_template, abort
from flask_login import login_required

from app import db
from app.models import Fornecedor
from app.services.comissao_fornecedor import (
    calcular_comissao_fornecedor, calcular_comissoes_todos_fornecedores,
)
from . import admin_bp, admin_required

logger = logging.getLogger(__name__)


@admin_bp.route("/comissoes")
@login_required
@admin_required
def comissoes():
    """Lista geral: 1 linha por fornecedor com receita + comissao agregada."""
    linhas = calcular_comissoes_todos_fornecedores()
    total_receita = sum(l["receita_total"] for l in linhas)
    total_comissao = sum(l["comissao_total"] for l in linhas)
    return render_template(
        "admin/comissoes.html",
        linhas=linhas,
        total_receita=total_receita,
        total_comissao=total_comissao,
    )


@admin_bp.route("/comissoes/<int:fornecedor_id>")
@login_required
@admin_required
def comissoes_detalhe(fornecedor_id):
    """Detalhe por fornecedor: por rodada + por dia."""
    fornecedor = db.session.get(Fornecedor, fornecedor_id)
    if fornecedor is None:
        abort(404)
    dados = calcular_comissao_fornecedor(fornecedor.id)
    return render_template(
        "admin/comissoes_detalhe.html",
        fornecedor=fornecedor,
        dados=dados,
    )
