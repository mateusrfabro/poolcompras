"""Programa de indicacao — dashboard da lanchonete + acao de resgatar."""
import logging
from datetime import datetime, timedelta, timezone

from flask import (
    render_template, redirect, url_for, flash, request, current_app,
)
from flask_login import login_required, current_user

from app import db, limiter
from app.auth_decorators import lanchonete_required
from app.models import Indicacao, Lanchonete
from app.services.indicacao import (
    garantir_codigo, indicacoes_da_lanchonete, calcular_status_recompensa,
    RECOMPENSA_INDICADAS_NECESSARIAS, RECOMPENSA_DIAS_ATIVA_MINIMO,
)
from app.services.notificacoes import post_telegram_raw, _escape
from . import perfil_bp

logger = logging.getLogger(__name__)


@perfil_bp.route("/indicacoes", methods=["GET"])
@login_required
@lanchonete_required
def indicacoes():
    """Dashboard "Minhas indicacoes": link copiavel + lista + status recompensa."""
    lanchonete = current_user.lanchonete
    codigo = garantir_codigo(lanchonete)
    base_url = request.host_url.rstrip("/")
    link_indicacao = f"{base_url}{url_for('auth.registro')}?ind={codigo}"

    lista = indicacoes_da_lanchonete(lanchonete.id)
    status = calcular_status_recompensa(lanchonete.id)

    return render_template(
        "perfil/indicacoes.html",
        lanchonete=lanchonete,
        codigo=codigo,
        link_indicacao=link_indicacao,
        indicacoes=lista,
        status=status,
        necessarias=RECOMPENSA_INDICADAS_NECESSARIAS,
    )


@perfil_bp.route("/indicacoes/resgatar", methods=["POST"])
@login_required
@lanchonete_required
@limiter.limit("5 per hour", error_message="Muitos resgates seguidos. Aguarde.")
def resgatar_recompensa():
    """Lanchonete clica 'Resgatar' — marca 3 indicacoes elegiveis como usadas
    e dispara notif Telegram pro admin aplicar o desconto manualmente.

    Idempotencia: se nao ha 3 elegiveis no momento do click, nao faz nada
    (evita race se 2 abas clicarem ao mesmo tempo).
    """
    lanchonete = current_user.lanchonete
    status = calcular_status_recompensa(lanchonete.id)
    if not status["pode_resgatar"]:
        flash("Voce ainda nao tem 3 indicadas elegiveis pra resgatar.", "warning")
        return redirect(url_for("perfil.indicacoes"))

    # Pega as 3 indicacoes mais antigas elegiveis (FIFO).
    # with_for_update bloqueia as rows ate o commit — Postgres respeita,
    # SQLite ignora (aceitavel em dev). Fecha race entre 2 abas/cliques
    # rapidos que poderiam consumir 6 indicacoes ao inves de 3.
    cutoff = datetime.now(timezone.utc) - timedelta(days=RECOMPENSA_DIAS_ATIVA_MINIMO)
    indicacoes_pra_consumir = (
        Indicacao.query
        .filter_by(indicador_lanchonete_id=lanchonete.id)
        .filter(Indicacao.recompensa_aplicada_em.is_(None))
        .filter(Indicacao.criado_em <= cutoff)
        .join(Lanchonete, Indicacao.indicada_lanchonete_id == Lanchonete.id)
        .filter(Lanchonete.ativa.is_(True))
        .order_by(Indicacao.criado_em.asc())
        .limit(RECOMPENSA_INDICADAS_NECESSARIAS)
        .with_for_update()
        .all()
    )
    if len(indicacoes_pra_consumir) < RECOMPENSA_INDICADAS_NECESSARIAS:
        # Race entre o calculo do status e o lock do select — improvavel
        # mas defensivo.
        flash("Estado mudou. Atualize a pagina.", "warning")
        return redirect(url_for("perfil.indicacoes"))

    agora = datetime.now(timezone.utc)
    for ind in indicacoes_pra_consumir:
        ind.recompensa_aplicada_em = agora
    db.session.commit()
    logger.info(
        "INDICACAO_RESGATADA lanchonete=%s qtd=%s",
        lanchonete.id, len(indicacoes_pra_consumir),
    )

    # Notifica admin via Telegram (se canal configurado) pra aplicar
    # desconto no proximo boleto. _escape() blinda HTML injection via
    # nome_fantasia controlado pelo user (parse_mode=HTML).
    chat_id = current_app.config.get("TELEGRAM_ADMIN_CHAT_ID")
    if chat_id:
        nome_safe = _escape(lanchonete.nome_fantasia)
        post_telegram_raw(
            chat_id,
            f"<b>Aggron — Recompensa de indicacao resgatada</b>\n\n"
            f"Lanchonete <b>{nome_safe}</b> (id {lanchonete.id}) "
            f"resgatou 1 mes gratis (3 indicadas elegiveis).\n\n"
            f"Acao manual: aplicar desconto no proximo boleto.",
            contexto=f"recompensa-indicacao lanchonete={lanchonete.id}",
        )

    flash(
        "Recompensa solicitada! Nossa equipe foi avisada e vai aplicar "
        "o mes gratis no seu proximo boleto.",
        "success",
    )
    return redirect(url_for("perfil.indicacoes"))
