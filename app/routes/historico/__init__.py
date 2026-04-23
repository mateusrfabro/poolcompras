"""Rotas da area 'Minhas Rodadas' da lanchonete logada.

Submodulos:
- listar.py: lista + export CSV das rodadas da lanchonete
- detalhe.py: detalhe expandido de 1 rodada (itens, timeline, insights, pagamento)
- analytics.py: Meu Resumo (KPIs) + Meu CMV (gasto/economia)
"""
from functools import wraps
from flask import Blueprint, flash, redirect, url_for
from flask_login import current_user

historico_bp = Blueprint("historico", __name__, url_prefix="/minhas-rodadas")


# Status que aparecem na aba Historico (nao queremos mostrar so "aberta" aqui)
STATUS_HISTORICO = ("finalizada", "cancelada", "fechada", "cotando")


def lanchonete_required(f):
    """Garante que o usuario logado eh uma lanchonete com cadastro completo.

    Substitui o padrao repetido de 3 blocos if que estava em cada rota.
    Redireciona pra main.dashboard se admin/fornecedor ou se lanchonete=None.
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        if current_user.is_admin or current_user.is_fornecedor:
            flash("Esta área é apenas para lanchonetes.", "warning")
            return redirect(url_for("main.dashboard"))
        if not current_user.lanchonete:
            flash("Complete seu cadastro primeiro.", "error")
            return redirect(url_for("main.dashboard"))
        return f(*args, **kwargs)
    return decorated


from . import listar, detalhe, analytics  # noqa: E402,F401
