"""Visao do fornecedor logado: quanto deve pagar pra Aggron de comissao.

Calculo on-the-fly via app.services.comissao_fornecedor.
"""
import logging

from flask import render_template
from flask_login import login_required, current_user

from app.services.comissao_fornecedor import calcular_comissao_fornecedor
from . import fornecedor_bp, fornecedor_required

logger = logging.getLogger(__name__)


@fornecedor_bp.route("/comissoes")
@login_required
@fornecedor_required
def comissoes():
    fornecedor = current_user.fornecedor
    dados = calcular_comissao_fornecedor(fornecedor.id) if fornecedor else None
    return render_template(
        "fornecedor/comissoes.html",
        fornecedor=fornecedor,
        dados=dados,
    )
