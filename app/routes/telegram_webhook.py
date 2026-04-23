"""Webhook do bot Telegram.

Quando `TELEGRAM_WEBHOOK_SECRET` esta configurado e o webhook registrado no
bot (via `flask set-telegram-webhook`), o Telegram entrega mensagens em
`POST /webhook/telegram/<secret>`.

Processa:
- `/start <token>`: valida token assinado, extrai user_id, salva chat_id
  e confirma no chat.
- `/start` sem token: responde com instrucoes pra ir no perfil.
- Demais mensagens: ignora silenciosamente (bot nao eh conversacional hoje).

Sem webhook configurado, o fluxo continua via `/perfil/telegram/confirmar`
(getUpdates on-demand + OTP). Webhook eh complementar — coexistem.

Retorna sempre 200 pro Telegram (senao ele retenta; nao queremos loop).
Loga erros internamente.
"""
import logging
import os

from flask import Blueprint, abort, jsonify, request, current_app
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from sqlalchemy import select

from app import db, limiter
from app.models import Usuario
from app.services.notificacoes import post_telegram_raw

logger = logging.getLogger(__name__)

telegram_webhook_bp = Blueprint("telegram_webhook", __name__)

# Tem que bater com o salt usado em perfil.py ao gerar o token de vinculacao
_VINCULAR_SALT = "vincular-telegram"
_VINCULAR_TTL_SEG = 600


def _vincular_serializer():
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"])


@telegram_webhook_bp.route("/webhook/telegram/<secret>", methods=["POST"])
@limiter.limit("60/minute")
def receber_update(secret):
    """Endpoint que o Telegram chama quando o webhook esta ativo.

    Rate-limit 60/min protege contra brute-force do secret na URL.
    Telegram em trafego normal manda <1/s pra um bot pequeno.
    """
    esperado = os.environ.get("TELEGRAM_WEBHOOK_SECRET")
    if not esperado or secret != esperado:
        abort(404)  # nao revela que a rota existe

    update = request.get_json(silent=True) or {}
    try:
        _processar_update(update)
    except Exception:  # pylint: disable=broad-except
        # Qualquer erro vira log — retornar 500 faz Telegram re-enviar e travar fila.
        logger.exception("TELEGRAM_WEBHOOK_EXC update=%s", str(update)[:300])

    return jsonify({"ok": True})


def _processar_update(update: dict):
    """Extrai o interessante do payload do Telegram e decide o que fazer.

    Payload tipico:
    {
        "update_id": 123,
        "message": {
            "message_id": 1,
            "from": {...},
            "chat": {"id": 987654321, ...},
            "text": "/start TOKEN",
            ...
        }
    }
    """
    msg = update.get("message") or update.get("edited_message") or {}
    texto = (msg.get("text") or "").strip()
    chat = msg.get("chat") or {}
    chat_id = chat.get("id")

    if not chat_id or not texto:
        return

    # So processamos /start [token]. Outros comandos/textos sao ignorados.
    if not texto.startswith("/start"):
        return

    partes = texto.split(maxsplit=1)
    token = partes[1].strip() if len(partes) == 2 else ""

    if not token:
        _enviar(chat_id,
                "Oi! Pra vincular seu Telegram ao PoolCompras, volte pro "
                "site, entre em Meu Perfil e clique em \"Conectar Telegram\". "
                "A vinculacao eh automatica.")
        return

    try:
        user_id = _vincular_serializer().loads(
            token, salt=_VINCULAR_SALT, max_age=_VINCULAR_TTL_SEG,
        )
    except SignatureExpired:
        _enviar(chat_id,
                "Link expirado. Gere um novo no site em Meu Perfil -> Conectar Telegram.")
        return
    except BadSignature:
        _enviar(chat_id,
                "Link invalido. Gere um novo no site em Meu Perfil -> Conectar Telegram.")
        return

    usuario = db.session.get(Usuario, user_id)
    if not usuario:
        _enviar(chat_id, "Usuario nao encontrado. Peca um novo link no site.")
        return

    # Se outro user ja usou este chat_id, bloqueia (unique constraint tambem
    # bloqueia, mas aqui damos mensagem amigavel antes do erro DB).
    ja_usado = db.session.execute(
        select(Usuario).where(
            Usuario.telegram_chat_id == chat_id,
            Usuario.id != usuario.id,
        )
    ).scalar_one_or_none()
    if ja_usado:
        _enviar(chat_id,
                "Este Telegram ja esta vinculado a outra conta do PoolCompras. "
                "Desvincule a conta antiga antes de vincular esta.")
        return

    usuario.telegram_chat_id = int(chat_id)
    db.session.commit()
    logger.info("TELEGRAM_WEBHOOK_VINCULADO usuario=%s chat_id=%s", usuario.id, chat_id)
    _enviar(chat_id,
            "<b>Telegram conectado!</b>\n\nVoce recebe notificacoes do "
            "PoolCompras aqui. Volte ao site e atualize a pagina pra ver "
            "o status atualizado.")


def _enviar(chat_id, texto: str):
    """Wrapper fino sobre services/notificacoes.post_telegram_raw."""
    post_telegram_raw(chat_id, texto, contexto="webhook")
