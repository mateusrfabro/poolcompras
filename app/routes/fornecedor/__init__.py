"""Rotas do fornecedor divididas por fase do fluxo.

O blueprint `fornecedor_bp` e o decorator `fornecedor_required` sao definidos aqui.
Os submodulos sao importados no fim do arquivo para registrar suas rotas.
"""
from functools import wraps
from flask import Blueprint, flash, redirect, url_for
from flask_login import current_user

fornecedor_bp = Blueprint("fornecedor", __name__, url_prefix="/fornecedor")


def fornecedor_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_fornecedor:
            flash("Acesso restrito a fornecedores.", "error")
            return redirect(url_for("main.dashboard"))
        return f(*args, **kwargs)

    return decorated


from . import dashboard, cotacao_partida, cotacao_final  # noqa: E402,F401
