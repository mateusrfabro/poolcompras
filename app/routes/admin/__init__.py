"""Rotas do admin divididas por dominio.

Blueprint + decorator vem de app.auth_decorators (fonte unica dos 3 papeis).
"""
from flask import Blueprint
from app.auth_decorators import admin_required  # noqa: F401 (re-export pra submodulos)

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


from . import produtos, fornecedores, lanchonetes, rodadas, moderacao, analytics  # noqa: E402,F401
