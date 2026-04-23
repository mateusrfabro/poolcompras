"""Camada de notificacoes (link recuperacao de senha, alertas, etc).

Hoje: loga o payload. No Bloco D vai plugar no bot Telegram (default do projeto).
E-mail via SMTP continua opcional — habilita apenas se SMTP_* estiverem em env.

Canal padrao do PoolCompras = Telegram bot (decisao 2026-04-22).
"""
import logging
import os
from flask import current_app

logger = logging.getLogger(__name__)


def enviar_link_recuperacao(usuario, link: str) -> bool:
    """Envia link de recuperacao de senha pelo canal disponivel.

    Ordem de preferencia:
    1. Telegram bot (se usuario.telegram_chat_id + TELEGRAM_BOT_TOKEN configurados)
    2. SMTP (se SMTP_HOST + SMTP_USER configurados)
    3. Log (fallback; admin ve no log e repassa manualmente)

    Returns:
        True se conseguiu enviar por canal real, False se caiu no fallback de log.
    """
    texto = (
        f"Ola, {usuario.nome_responsavel}!\n\n"
        f"Recebemos um pedido pra redefinir sua senha no PoolCompras.\n"
        f"Clique no link abaixo (valido por 1 hora):\n\n"
        f"{link}\n\n"
        f"Se voce nao solicitou, ignore esta mensagem."
    )

    # 1. Telegram (placeholder — implementa quando bot estiver configurado)
    chat_id = getattr(usuario, "telegram_chat_id", None)
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if chat_id and bot_token:
        # TODO(bloco-telegram): implementar POST pra api.telegram.org/bot<token>/sendMessage
        logger.info("notif.telegram.skipped (implementacao pendente) user=%s", usuario.id)

    # 2. SMTP (placeholder)
    if os.environ.get("SMTP_HOST") and os.environ.get("SMTP_USER"):
        # TODO(bloco-smtp): implementar envio via smtplib
        logger.info("notif.smtp.skipped (implementacao pendente) user=%s", usuario.id)

    # 3. Fallback: log estruturado pro admin pegar manualmente em DEV
    # Em prod (gunicorn + journald) vira rastro auditavel.
    app = current_app._get_current_object() if current_app else None
    if app and app.debug:
        logger.warning(
            "RECUPERACAO_SENHA usuario=%s email=%s link=%s\n%s",
            usuario.id, usuario.email, link, texto,
        )
    else:
        logger.info(
            "RECUPERACAO_SENHA usuario=%s email=%s link=%s",
            usuario.id, usuario.email, link,
        )
    return False
