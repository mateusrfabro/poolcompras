"""Decorators centralizados pra protecao de rotas por papel.

Substitui os 3 helpers quase identicos que existiam em:
- app/routes/admin/__init__.py::admin_required
- app/routes/fornecedor/__init__.py::fornecedor_required
- app/routes/historico/__init__.py::lanchonete_required

Os antigos continuam existindo como aliases pra nao quebrar imports.
"""
from functools import wraps
from flask import flash, redirect, url_for
from flask_login import current_user


def role_required(role: str, check_cadastro: bool = False):
    """Gera decorator que exige current_user com o papel `role`.

    Args:
        role: "admin" | "lanchonete" | "fornecedor".
        check_cadastro: Se True, tambem exige que lanchonete/fornecedor
            tenham cadastro completo (objeto vinculado nao-null).

    Mensagem e redirect sao padronizados.
    """
    check_fn = {
        "admin":      lambda u: u.is_admin,
        "lanchonete": lambda u: u.is_lanchonete and (not check_cadastro or u.lanchonete),
        "fornecedor": lambda u: u.is_fornecedor and (not check_cadastro or u.fornecedor),
    }[role]

    mensagem = {
        "admin":      "Acesso restrito a administradores.",
        "lanchonete": "Esta área é apenas para lanchonetes.",
        "fornecedor": "Acesso restrito a fornecedores.",
    }[role]

    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if not check_fn(current_user):
                flash(mensagem, "warning" if role == "lanchonete" else "error")
                return redirect(url_for("main.dashboard"))
            if check_cadastro and role != "admin":
                vinculado = current_user.lanchonete if role == "lanchonete" else current_user.fornecedor
                if not vinculado:
                    flash("Complete seu cadastro primeiro.", "error")
                    return redirect(url_for("main.dashboard"))
            return f(*args, **kwargs)
        return decorated
    return decorator


# Atalhos pros papeis mais comuns
admin_required      = role_required("admin")
fornecedor_required = role_required("fornecedor")
lanchonete_required = role_required("lanchonete", check_cadastro=True)
