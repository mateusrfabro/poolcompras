"""Blueprint do CRM (pipeline de leads).

Acesso: admin (ve tudo) + vendedor (ve so os proprios leads).
"""
from flask import Blueprint
from app.auth_decorators import vendedor_ou_admin_required  # noqa: F401

crm_bp = Blueprint("crm", __name__, url_prefix="/crm")


from . import kanban, leads  # noqa: E402,F401
