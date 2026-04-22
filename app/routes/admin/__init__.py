"""Rotas do admin divididas por dominio.

O blueprint `admin_bp` e o decorator `admin_required` sao definidos aqui.
Os submodulos sao importados no fim do arquivo para registrar suas rotas
no blueprint.
"""
from functools import wraps
from flask import Blueprint, flash, redirect, url_for
from flask_login import current_user

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_admin:
            flash("Acesso restrito a administradores.", "error")
            return redirect(url_for("main.dashboard"))
        return f(*args, **kwargs)

    return decorated


from . import produtos, fornecedores, lanchonetes, rodadas, moderacao, analytics  # noqa: E402,F401
