"""Rotas do fornecedor divididas por fase do fluxo.

Blueprint + decorator vem de app.auth_decorators.
"""
from flask import Blueprint
from app.auth_decorators import fornecedor_required  # noqa: F401

fornecedor_bp = Blueprint("fornecedor", __name__, url_prefix="/fornecedor")


from . import dashboard, cotacao_partida, cotacao_final  # noqa: E402,F401
