"""Kanban de rodadas (visao admin operacional do dia).

Permite ver TODAS rodadas em tabuleiro por status + drill-down em cada
rodada pra ver quem ja fez o que (cobranca individual).
"""
import logging

from flask import render_template, abort
from flask_login import login_required

from app.services.rodada_kanban import (
    rodadas_por_status, situacao_rodada,
    STATUS_KANBAN_RODADAS, STATUS_LABELS,
)
from . import admin_bp, admin_required

logger = logging.getLogger(__name__)


@admin_bp.route("/rodadas/kanban")
@login_required
@admin_required
def rodadas_kanban():
    grupos = rodadas_por_status()
    return render_template(
        "admin/rodadas_kanban.html",
        grupos=grupos,
        status_ordem=STATUS_KANBAN_RODADAS,
        status_labels=STATUS_LABELS,
    )


@admin_bp.route("/rodadas/<int:rodada_id>/situacao")
@login_required
@admin_required
def rodada_situacao(rodada_id):
    """Drill-down: lista de lanchonetes + fornecedores com etapa atual."""
    dados = situacao_rodada(rodada_id)
    if not dados:
        abort(404)
    return render_template("admin/rodada_situacao.html", **dados)
