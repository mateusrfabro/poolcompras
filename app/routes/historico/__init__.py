"""Rotas da area 'Minhas Rodadas' da lanchonete logada.

Blueprint + decorator vem de app.auth_decorators (fonte unica).
"""
from flask import Blueprint
from app.auth_decorators import lanchonete_required  # noqa: F401

historico_bp = Blueprint("historico", __name__, url_prefix="/minhas-rodadas")

STATUS_HISTORICO = ("finalizada", "cancelada", "fechada", "cotando")


from . import listar, detalhe, analytics  # noqa: E402,F401
