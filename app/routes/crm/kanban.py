"""Kanban do CRM — view principal."""
import logging

from flask import abort, render_template, request
from flask_login import login_required, current_user

from app import db
from app.models import Lead, Vendedor
from app.services.crm_pipeline import leads_agrupados, kpis_vendedores
from . import crm_bp, vendedor_ou_admin_required

logger = logging.getLogger(__name__)


@crm_bp.route("/")
@login_required
@vendedor_ou_admin_required
def kanban():
    """Kanban com 5 colunas + filtro por vendedor + KPIs no topo.

    Admin: ve tudo, pode filtrar por vendedor (?vendedor_id=X).
    Vendedor: ve so os proprios — filtro forcado, ignora ?vendedor_id.
    """
    if current_user.is_admin:
        vendedor_filtro_id = request.args.get("vendedor_id", "").strip()
        try:
            vendedor_filtro_id = int(vendedor_filtro_id) if vendedor_filtro_id else None
        except ValueError:
            vendedor_filtro_id = None
        vendedores_lista = db.session.scalars(
            db.select(Vendedor).where(Vendedor.ativo.is_(True))
            .order_by(Vendedor.nome)
        ).all()
    else:
        # Vendedor logado: filtro forcado pro proprio id (anti-IDOR).
        if not current_user.vendedor:
            # Caso edge: usuario tipo='vendedor' sem registro Vendedor (legacy).
            abort(403)
        vendedor_filtro_id = current_user.vendedor.id
        vendedores_lista = []

    grupos = leads_agrupados(vendedor_id=vendedor_filtro_id)
    kpis = kpis_vendedores(vendedor_id=vendedor_filtro_id)

    return render_template(
        "crm/kanban.html",
        grupos=grupos,
        kpis=kpis,
        vendedor_filtro_id=vendedor_filtro_id,
        vendedores=vendedores_lista,
        is_admin=current_user.is_admin,
        status_ordem=Lead.STATUS_KANBAN_ORDEM,
        status_labels={
            Lead.STATUS_FRIO:      "Frio",
            Lead.STATUS_MORNO:     "Morno",
            Lead.STATUS_QUENTE:    "Quente",
            Lead.STATUS_FECHADO:   "Fechado",
            Lead.STATUS_CANCELADO: "Cancelado",
        },
        status_descricoes={
            Lead.STATUS_FRIO:      "Primeiro contato, prospecção inicial.",
            Lead.STATUS_MORNO:     "Conversando, reunião ou visita marcada.",
            Lead.STATUS_QUENTE:    "Minuta enviada, aguardando assinatura.",
            Lead.STATUS_FECHADO:   "Assinou — vira cliente real.",
            Lead.STATUS_CANCELADO: "Não vai fechar (motivo no log).",
        },
    )
