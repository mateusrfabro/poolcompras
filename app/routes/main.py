from flask import Blueprint, render_template, redirect, url_for, jsonify
from flask_login import login_required, current_user
from sqlalchemy import func, select, text
from app import db
from app.models import (
    Lanchonete, Rodada, ItemPedido, Produto,
    ParticipacaoRodada, Fornecedor,
)
from app.services.dashboard_lanchonete import dashboard_data
from app.services.rodada_corrente import rodada_corrente_aberta
from app.services.kpis_admin import (
    total_lanchonetes_ativas, total_produtos_ativos,
    pedidos_da_rodada, qtd_lanchonetes_da_rodada,
)

main_bp = Blueprint("main", __name__)


@main_bp.route("/health")
def health():
    """Healthcheck: retorna 200 se app + DB estao ok. Sem auth.

    NUNCA inclui detalhes do erro na resposta — endpoint publico, atacante
    nao precisa saber se DB caiu por timeout, auth ou driver. Loga
    internamente pra debug.
    """
    import logging
    try:
        db.session.execute(text("SELECT 1"))
        return jsonify({"status": "ok", "db": "ok"}), 200
    except Exception:
        logging.getLogger(__name__).exception("HEALTH_DB_FAIL")
        return jsonify({"status": "error", "db": "error"}), 500


@main_bp.route("/")
def index():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    # Prova social: numeros reais do DB pra criar credibilidade no visitante
    # anonimo. 3 queries simples sem join — leves o suficiente pra rodar a
    # cada hit na home publica.
    prova_social = {
        "lanchonetes": db.session.scalar(
            select(func.count(Lanchonete.id)).where(Lanchonete.ativa.is_(True))
        ) or 0,
        "fornecedores": db.session.scalar(
            select(func.count(Fornecedor.id)).where(Fornecedor.ativo.is_(True))
        ) or 0,
        "rodadas": db.session.scalar(
            select(func.count(Rodada.id)).where(Rodada.status == "finalizada")
        ) or 0,
    }
    return render_template("index.html", prova_social=prova_social)


@main_bp.route("/dashboard")
@login_required
def dashboard():
    # Fornecedor vai para o painel dele
    if current_user.is_fornecedor:
        return redirect(url_for("fornecedor.dashboard"))

    # Admin
    if current_user.is_admin:
        # KPIs cacheados (TTL 30s) — antes 4 queries síncronas a cada hit.
        total_lanchonetes = total_lanchonetes_ativas()
        total_produtos = total_produtos_ativos()
        rodada_aberta = rodada_corrente_aberta()

        pedidos_rodada = 0
        qtd_lanchonetes_rodada = 0
        if rodada_aberta:
            pedidos_rodada = pedidos_da_rodada(rodada_aberta.id)
            qtd_lanchonetes_rodada = qtd_lanchonetes_da_rodada(rodada_aberta.id)

        return render_template(
            "dashboard_admin.html",
            total_lanchonetes=total_lanchonetes,
            total_produtos=total_produtos,
            rodada_aberta=rodada_aberta,
            pedidos_rodada=pedidos_rodada,
            qtd_lanchonetes_rodada=qtd_lanchonetes_rodada,
        )

    # Lanchonete
    lanchonete = current_user.lanchonete
    rodada_aberta = rodada_corrente_aberta()

    participacao_atual = None
    if rodada_aberta and lanchonete:
        participacao_atual = db.session.execute(
            select(ParticipacaoRodada).where(
                ParticipacaoRodada.rodada_id == rodada_aberta.id,
                ParticipacaoRodada.lanchonete_id == lanchonete.id,
            )
        ).scalar_one_or_none()

    meus_pedidos = []
    if rodada_aberta and lanchonete:
        meus_pedidos = db.session.scalars(
            select(ItemPedido).where(
                ItemPedido.rodada_id == rodada_aberta.id,
                ItemPedido.lanchonete_id == lanchonete.id,
            )
        ).all()

    # KPIs + pendencias + ultimas rodadas (logica em service)
    kpis = {}
    pendencias = []
    ultimas_rodadas = []
    if lanchonete:
        data = dashboard_data(lanchonete.id)
        pendencias = data["pendencias"]
        kpis = data["kpis"]
        ultimas_rodadas = data["ultimas_rodadas"]

    return render_template(
        "dashboard.html",
        lanchonete=lanchonete,
        rodada_aberta=rodada_aberta,
        meus_pedidos=meus_pedidos,
        kpis=kpis,
        pendencias=pendencias,
        ultimas_rodadas=ultimas_rodadas,
        participacao_atual=participacao_atual,
    )
