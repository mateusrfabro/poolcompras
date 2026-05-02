"""Camada de notificacoes via Telegram bot (canal default do projeto).

- `enviar_telegram(usuario, texto, sensitive=False)`: helper generico. Se
  o usuario tiver `telegram_chat_id` e env `TELEGRAM_BOT_TOKEN`, faz POST
  pra API do Telegram. Senao, fallback de log. Quando `sensitive=True`
  (ex: OTP), nunca loga o conteudo nem em DEBUG — so registra a tentativa.

- `enviar_link_recuperacao(usuario, link)`: chama `enviar_telegram` com texto
  pre-formatado pra reset de senha. Marcado sensitive (link tem token).

- `notificar_evento(usuario, titulo, detalhes)`: helper pros eventos do fluxo.

Docs da API: https://core.telegram.org/bots/api#sendmessage
"""
import logging
import os

import requests
from flask import current_app
from sqlalchemy.orm import joinedload

from app import db
from app.models import (
    Lanchonete, Fornecedor, RodadaProduto, ItemPedido, Cotacao,
)

logger = logging.getLogger(__name__)

_TELEGRAM_TIMEOUT_SEG = 5  # evita travar a request se api.telegram.org cair
_TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


def _tem_canal_ativo(usuario) -> bool:
    """True se o usuario configurou telegram_chat_id E temos TELEGRAM_BOT_TOKEN."""
    return bool(
        getattr(usuario, "telegram_chat_id", None)
        and os.environ.get("TELEGRAM_BOT_TOKEN")
    )


def post_telegram_raw(chat_id, texto: str, contexto: str = "") -> bool:
    """Envia texto pra chat_id bruto. Nao exige objeto Usuario.

    Usado por enviar_telegram (com Usuario) e pelo webhook (so tem chat_id).
    `contexto` aparece nos logs (ex: "usuario=3" ou "webhook"). Retorna True
    se API respondeu 200+ok. Nao levanta.
    """
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        return False
    url = _TELEGRAM_API.format(token=token)
    payload = {
        "chat_id": chat_id,
        "text": texto,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }
    ctx = f" {contexto}" if contexto else ""
    try:
        r = requests.post(url, json=payload, timeout=_TELEGRAM_TIMEOUT_SEG)
        if r.status_code == 200 and r.json().get("ok"):
            logger.info("TELEGRAM_OK%s chat=%s", ctx, chat_id)
            return True
        logger.warning(
            "TELEGRAM_FAIL%s chat=%s status=%s body=%s",
            ctx, chat_id, r.status_code, r.text[:200],
        )
    except requests.RequestException as e:
        logger.warning("TELEGRAM_EXC%s chat=%s err=%s", ctx, chat_id, e)
    return False


def enviar_telegram(usuario, texto: str, sensitive: bool = False) -> bool:
    """Envia uma mensagem de texto pro chat_id do usuario via bot.

    Args:
        sensitive: quando True (OTP, link de reset), nunca loga o conteudo
            no fallback — nem em DEBUG. So registra tentativa anonima.

    Returns:
        True se a API Telegram retornou 200. False se fallou ou se canal
        nao esta configurado.

    Nao levanta excecao — notificacao eh best-effort e nao pode bloquear
    o fluxo de negocio.
    """
    if not _tem_canal_ativo(usuario):
        _logar_fallback(usuario, texto, sensitive=sensitive)
        return False

    ok = post_telegram_raw(usuario.telegram_chat_id, texto,
                           contexto=f"usuario={usuario.id}")
    if not ok:
        _logar_fallback(usuario, texto, sensitive=sensitive)
    return ok


def _logar_fallback(usuario, texto: str, sensitive: bool = False):
    """Fallback: registra no log quando canal Telegram nao ta pronto.

    Em DEBUG/TESTING + sensitive=False: loga texto completo (admin/test pegam do log).
    Em prod ou sensitive=True: loga apenas que houve tentativa (nao vaza
    OTP, link de reset, ou outros segredos).
    """
    if sensitive:
        # NUNCA loga o conteudo — mesmo em DEBUG/TESTING.
        logger.info(
            "NOTIF_FALLBACK_SENSITIVE usuario=%s (conteudo omitido)",
            usuario.id,
        )
        return

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
    """Envia link de recuperacao de senha. Canal preferencial: Telegram.
    Marcado sensitive: o link contem token assinado — nunca cair em log."""
    texto = (
        f"Olá, {_escape(usuario.nome_responsavel)}!\n\n"
        f"Recebemos um pedido pra redefinir sua senha no Aggron.\n"
        f"Clique no link abaixo (válido por 1 hora):\n\n"
        f"{link}\n\n"
        f"Se você não solicitou, ignore esta mensagem."
    )
    return enviar_telegram(usuario, texto, sensitive=True)


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
    texto += "\n\n— Aggron"
    return enviar_telegram(usuario, texto)


def _escape(txt: str) -> str:
    """Escape minimo pra HTML parse_mode do Telegram (so &, <, >)."""
    if not txt:
        return ""
    return str(txt).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# =============================================================================
# Notificacoes em massa por transicao de status de rodada.
#
# Convencao: cada helper retorna a quantidade de mensagens disparadas. Imports
# de Models ficam locais pra evitar import circular (notificacoes <-> models).
# =============================================================================

def notificar_fornecedores_nova_rodada(rodada) -> int:
    """Avisa fornecedores ATIVOS que tem rodada nova esperando preco de partida.

    Disparado quando admin envia o catalogo (status -> aguardando_cotacao).
    """
    titulo = "Nova rodada para cotar"
    detalhes = (
        f"O catálogo da rodada '{rodada.nome}' foi liberado. "
        f"Acesse o painel pra enviar seu preço de partida."
    )
    enviadas = 0
    # joinedload(responsavel) evita N+1: 1 query traz todos fornecedores +
    # responsaveis. Sem isso, 50 fornecedores = 50 SELECTs em usuarios.
    fornecedores = (
        Fornecedor.query
        .options(joinedload(Fornecedor.responsavel))
        .filter_by(ativo=True)
        .all()
    )
    for f in fornecedores:
        if f.responsavel and notificar_evento(f.responsavel, titulo, detalhes):
            enviadas += 1
    logger.info("NOTIF_RODADA_NOVA rodada=%s enviadas=%s", rodada.id, enviadas)
    return enviadas


def notificar_lanchonetes_rodada_aberta(rodada) -> int:
    """Avisa lanchonetes ATIVAS que a rodada ta aberta pra fazer pedidos."""
    titulo = "Rodada aberta"
    detalhes = (
        f"A rodada '{rodada.nome}' está aberta para pedidos. "
        f"Monte seu pedido antes do fechamento."
    )
    enviadas = 0
    lanchonetes = (
        Lanchonete.query
        .options(joinedload(Lanchonete.responsavel))
        .filter_by(ativa=True)
        .all()
    )
    for l in lanchonetes:
        if l.responsavel and notificar_evento(l.responsavel, titulo, detalhes):
            enviadas += 1
    logger.info("NOTIF_RODADA_ABERTA rodada=%s enviadas=%s", rodada.id, enviadas)
    return enviadas


def notificar_fornecedores_cotacao_final(rodada) -> int:
    """Avisa fornecedores que ja cotaram preco de partida que e hora do preco
    final (com volumes reais)."""
    forn_ids = {
        fid for (fid,) in db.session.query(RodadaProduto.adicionado_por_fornecedor_id)
            .filter(RodadaProduto.rodada_id == rodada.id)
            .filter(RodadaProduto.adicionado_por_fornecedor_id.isnot(None))
            .filter(RodadaProduto.preco_partida.isnot(None))
            .distinct().all()
    }
    if not forn_ids:
        return 0
    titulo = "Cotação final disponível"
    detalhes = (
        f"A coleta de pedidos da rodada '{rodada.nome}' foi encerrada. "
        f"Acesse o painel pra enviar seu preço final com os volumes reais."
    )
    enviadas = 0
    fornecedores = (
        Fornecedor.query
        .options(joinedload(Fornecedor.responsavel))
        .filter(Fornecedor.id.in_(forn_ids))
        .all()
    )
    for f in fornecedores:
        if f.responsavel and notificar_evento(f.responsavel, titulo, detalhes):
            enviadas += 1
    logger.info("NOTIF_COTACAO_FINAL rodada=%s enviadas=%s", rodada.id, enviadas)
    return enviadas


def notificar_lanchonetes_cotacao_aprovada(rodada, fornecedor) -> int:
    """Avisa lanchonetes que pediram nessa rodada que tem proposta nova
    aprovada do fornecedor X."""
    lanch_ids = {
        lid for (lid,) in db.session.query(ItemPedido.lanchonete_id)
            .filter(ItemPedido.rodada_id == rodada.id)
            .distinct().all()
    }
    if not lanch_ids:
        return 0
    titulo = "Proposta de fornecedor disponível"
    detalhes = (
        f"O fornecedor {fornecedor.razao_social} teve cotação aprovada na "
        f"rodada '{rodada.nome}'. Acesse o painel pra aceitar ou recusar a proposta."
    )
    enviadas = 0
    lanchonetes = (
        Lanchonete.query
        .options(joinedload(Lanchonete.responsavel))
        .filter(Lanchonete.id.in_(lanch_ids))
        .all()
    )
    for l in lanchonetes:
        if l.responsavel and notificar_evento(l.responsavel, titulo, detalhes):
            enviadas += 1
    logger.info("NOTIF_PROPOSTA_DISPONIVEL rodada=%s fornecedor=%s enviadas=%s",
                rodada.id, fornecedor.id, enviadas)
    return enviadas


def notificar_cancelamento(rodada) -> int:
    """Avisa lanchonetes que pediram + fornecedores que cotaram que a rodada
    foi cancelada."""
    lanch_ids = {
        lid for (lid,) in db.session.query(ItemPedido.lanchonete_id)
            .filter(ItemPedido.rodada_id == rodada.id).distinct().all()
    }
    forn_ids = {
        fid for (fid,) in db.session.query(Cotacao.fornecedor_id)
            .filter(Cotacao.rodada_id == rodada.id).distinct().all()
    }
    titulo = "Rodada cancelada"
    detalhes = f"A rodada '{rodada.nome}' foi cancelada pelo administrador."
    enviadas = 0
    if lanch_ids:
        lanchonetes = (
            Lanchonete.query
            .options(joinedload(Lanchonete.responsavel))
            .filter(Lanchonete.id.in_(lanch_ids))
            .all()
        )
        for l in lanchonetes:
            if l.responsavel and notificar_evento(l.responsavel, titulo, detalhes):
                enviadas += 1
    if forn_ids:
        fornecedores = (
            Fornecedor.query
            .options(joinedload(Fornecedor.responsavel))
            .filter(Fornecedor.id.in_(forn_ids))
            .all()
        )
        for f in fornecedores:
            if f.responsavel and notificar_evento(f.responsavel, titulo, detalhes):
                enviadas += 1
    logger.info("NOTIF_RODADA_CANCELADA rodada=%s enviadas=%s",
                rodada.id, enviadas)
    return enviadas
