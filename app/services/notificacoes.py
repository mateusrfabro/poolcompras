"""Camada de notificacoes via Telegram bot (canal default do projeto).

- `enviar_telegram(usuario, texto)`: helper generico. Se o usuario tiver
  `telegram_chat_id` preenchido e a env `TELEGRAM_BOT_TOKEN` existir, faz POST
  pra API do Telegram. Senao, cai no fallback de log.

- `enviar_link_recuperacao(usuario, link)`: chama `enviar_telegram` com texto
  pre-formatado pra reset de senha.

- `notificar_evento(usuario, titulo, detalhes)`: helper pros eventos do fluxo
  (proposta aprovada, pagamento confirmado, cotacao devolvida, etc).

Docs da API: https://core.telegram.org/bots/api#sendmessage
"""
import logging
import os

import requests
from flask import current_app

logger = logging.getLogger(__name__)

_TELEGRAM_TIMEOUT_SEG = 5  # evita travar a request se api.telegram.org cair
_TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


def _tem_canal_ativo(usuario) -> bool:
    """True se o usuario configurou telegram_chat_id E temos TELEGRAM_BOT_TOKEN."""
    return bool(
        getattr(usuario, "telegram_chat_id", None)
        and os.environ.get("TELEGRAM_BOT_TOKEN")
    )


def enviar_telegram(usuario, texto: str) -> bool:
    """Envia uma mensagem de texto pro chat_id do usuario via bot.

    Returns:
        True se a API Telegram retornou 200. False se fallou ou se canal
        nao esta configurado (cai no fallback de log).

    Nao levanta excecao — notificacao eh best-effort e nao pode bloquear
    o fluxo de negocio.
    """
    if not _tem_canal_ativo(usuario):
        _logar_fallback(usuario, texto)
        return False

    token = os.environ["TELEGRAM_BOT_TOKEN"]
    url = _TELEGRAM_API.format(token=token)
    payload = {
        "chat_id": usuario.telegram_chat_id,
        "text": texto,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }
    try:
        r = requests.post(url, json=payload, timeout=_TELEGRAM_TIMEOUT_SEG)
        if r.status_code == 200 and r.json().get("ok"):
            logger.info("TELEGRAM_OK usuario=%s", usuario.id)
            return True
        logger.warning(
            "TELEGRAM_FAIL usuario=%s status=%s body=%s",
            usuario.id, r.status_code, r.text[:200],
        )
    except requests.RequestException as e:
        logger.warning("TELEGRAM_EXC usuario=%s err=%s", usuario.id, e)

    _logar_fallback(usuario, texto)
    return False


def _logar_fallback(usuario, texto: str):
    """Fallback: registra no log quando canal Telegram nao ta pronto.

    Em DEBUG/TESTING: loga texto completo (admin/test pegam do log).
    Em prod: loga apenas que houve tentativa (nao vaza tokens de reset).
    """
    app = current_app._get_current_object() if current_app else None
    dev_like = bool(app and (app.debug or app.config.get("TESTING")))
    if dev_like:
        logger.warning(
            "NOTIF_FALLBACK usuario=%s email=%s\n%s",
            usuario.id, usuario.email, texto,
        )
    else:
        logger.info(
            "NOTIF_FALLBACK_SOLICITADA usuario=%s (canal nao configurado)",
            usuario.id,
        )


def enviar_link_recuperacao(usuario, link: str) -> bool:
    """Envia link de recuperacao de senha. Canal preferencial: Telegram."""
    texto = (
        f"Olá, {_escape(usuario.nome_responsavel)}!\n\n"
        f"Recebemos um pedido pra redefinir sua senha no PoolCompras.\n"
        f"Clique no link abaixo (válido por 1 hora):\n\n"
        f"{link}\n\n"
        f"Se você não solicitou, ignore esta mensagem."
    )
    return enviar_telegram(usuario, texto)


def notificar_evento(usuario, titulo: str, detalhes: str = "") -> bool:
    """Notifica o usuario sobre um evento do fluxo (proposta, pagto, etc).

    Args:
        usuario: Usuario dono da notificacao
        titulo: linha principal da mensagem (ex: "Proposta aprovada")
        detalhes: opcional, texto adicional (ex: nome da rodada)
    """
    texto = f"<b>{_escape(titulo)}</b>"
    if detalhes:
        texto += f"\n\n{_escape(detalhes)}"
    texto += "\n\n— PoolCompras"
    return enviar_telegram(usuario, texto)


def _escape(txt: str) -> str:
    """Escape minimo pra HTML parse_mode do Telegram (so &, <, >)."""
    if not txt:
        return ""
    return str(txt).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
