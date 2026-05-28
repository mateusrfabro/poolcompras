"""Tela 'Minha assinatura' da lanchonete.

GET /perfil/assinatura — vigencia do contrato + 12 parcelas com status
e botao de download da NF (quando admin sobe). Inspirada na pagina
de assinatura do Stripe.

Sem operacoes mutantes aqui (cliente nao marca pago, nao cancela
contrato pelo painel — pelo menos no MVP). Cancelamento eh fluxo
externo via Aggron.
"""
from __future__ import annotations

import logging

from flask import render_template, abort
from flask_login import login_required, current_user
from sqlalchemy.orm import joinedload

from app.auth_decorators import lanchonete_required
from app.models import Assinatura
from . import perfil_bp

logger = logging.getLogger(__name__)


@perfil_bp.route("/assinatura")
@login_required
@lanchonete_required
def assinatura():
    """Mostra contrato ativo + 12 parcelas. Se nao tem, oferece pedir."""
    lanchonete = current_user.lanchonete
    if lanchonete is None:
        abort(404)

    # 1 contrato ativo por lanchonete (MVP). Pega o mais recente caso
    # tenha varias historias (cancelado + ativo).
    a = (
        Assinatura.query
        .filter_by(lanchonete_id=lanchonete.id)
        .options(joinedload(Assinatura.faturas))
        .order_by(Assinatura.criado_em.desc())
        .first()
    )

    contagens = {
        "total": 0, "pagas": 0, "pendentes": 0,
        "atrasadas": 0, "canceladas": 0,
    }
    if a:
        contagens["total"] = len(a.faturas)
        for f in a.faturas:
            if f.status == "paga":
                contagens["pagas"] += 1
            elif f.status == "atrasada":
                contagens["atrasadas"] += 1
            elif f.status == "cancelada":
                contagens["canceladas"] += 1
            else:
                contagens["pendentes"] += 1

    return render_template(
        "perfil/assinatura.html",
        assinatura=a,
        contagens=contagens,
    )
