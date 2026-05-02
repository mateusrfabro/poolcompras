"""Comandos CLI pra gerenciar o webhook do bot Telegram.

Uso:
    flask telegram set-webhook
        -> le TELEGRAM_BOT_TOKEN + TELEGRAM_WEBHOOK_URL + TELEGRAM_WEBHOOK_SECRET
           do env e chama api.telegram.org/bot<token>/setWebhook

    flask telegram remove-webhook
        -> desregistra o webhook (volta pro modo getUpdates on-demand)

    flask telegram info
        -> mostra info do bot + webhook atual
"""
import os

import click
import requests
from flask import Blueprint
from flask.cli import with_appcontext


telegram_cli_bp = Blueprint("telegram", __name__, cli_group="telegram")

_API = "https://api.telegram.org/bot{token}"


def _token():
    t = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not t:
        raise click.ClickException("TELEGRAM_BOT_TOKEN nao definido no env/.env")
    return t


def _call(endpoint, **params):
    url = f"{_API.format(token=_token())}/{endpoint}"
    r = requests.get(url, params=params, timeout=10)
    try:
        data = r.json()
    except ValueError:
        raise click.ClickException(f"resposta invalida do Telegram: {r.text[:200]}")
    if not data.get("ok"):
        raise click.ClickException(f"Telegram retornou erro: {data}")
    return data


@telegram_cli_bp.cli.command("set-webhook")
@with_appcontext
def set_webhook():
    """Registra webhook em https://TELEGRAM_WEBHOOK_URL/webhook/telegram/<SECRET>."""
    url_base = os.environ.get("TELEGRAM_WEBHOOK_URL", "").rstrip("/")
    secret = os.environ.get("TELEGRAM_WEBHOOK_SECRET")
    if not url_base:
        raise click.ClickException(
            "TELEGRAM_WEBHOOK_URL nao definido (ex: https://aggron.com.br)"
        )
    if not secret:
        raise click.ClickException(
            "TELEGRAM_WEBHOOK_SECRET nao definido (gere 32+ chars aleatorios)"
        )

    alvo = f"{url_base}/webhook/telegram/{secret}"
    data = _call("setWebhook", url=alvo, drop_pending_updates="true")
    click.echo(f"[ok] webhook registrado -> {alvo}")
    click.echo(f"     description: {data.get('description', '-')}")


@telegram_cli_bp.cli.command("remove-webhook")
@with_appcontext
def remove_webhook():
    """Remove webhook (volta a valer getUpdates on-demand)."""
    data = _call("deleteWebhook", drop_pending_updates="true")
    click.echo(f"[ok] webhook removido — {data.get('description', '-')}")


@telegram_cli_bp.cli.command("info")
@with_appcontext
def info():
    """Mostra info do bot + webhook atual."""
    me = _call("getMe")["result"]
    click.echo(f"Bot: @{me.get('username')}  (id={me.get('id')})")

    wh = _call("getWebhookInfo")["result"]
    url = wh.get("url") or "<nenhum — modo getUpdates>"
    click.echo(f"Webhook: {url}")
    if wh.get("last_error_message"):
        click.echo(f"  ultimo erro: {wh['last_error_message']}")
    if wh.get("pending_update_count"):
        click.echo(f"  pendentes: {wh['pending_update_count']}")
