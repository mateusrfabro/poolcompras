"""Edicao de perfil: o proprio usuario corrige seus dados cadastrais + senha.

Regras:
- Email eh readonly (troca de e-mail eh feature separada por nao ser trivial)
- CNPJ da lanchonete: editavel (erros de cadastro precisam ser corrigidos por ela)
- Troca de senha eh opcional: se senha_nova vazia, nao altera
- Troca de senha exige senha_atual correta (protege de sessao sequestrada)
"""
import hashlib
import hmac
import logging
import os
import secrets
from datetime import datetime, timedelta, timezone

import requests
from flask import Blueprint, render_template, redirect, url_for, flash, request, session, current_app
from flask_login import login_required, current_user
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from werkzeug.security import check_password_hash, generate_password_hash

from app import db, limiter
from app.services.notificacoes import enviar_telegram

logger = logging.getLogger(__name__)

perfil_bp = Blueprint("perfil", __name__, url_prefix="/perfil")

# Vinculacao Telegram — fluxo em 2 etapas:
#   1. Descoberta do chat_id (via deep link t.me/bot?start=<token>  OU  colado manualmente)
#   2. Confirmacao por OTP: sistema envia codigo de 6 digitos pro chat_id
#      descoberto. So salva Usuario.telegram_chat_id se o user colar o codigo
#      correto de volta. Fecha o vetor "atacante cola chat_id alheio".
_TELEGRAM_SALT = "vincular-telegram"
_TELEGRAM_TTL_SEG = 600  # 10 min — tempo pra abrir Telegram e dar start
_TELEGRAM_OTP_TTL_SEG = 600
_TELEGRAM_OTP_LEN = 6


def _bot_username():
    return current_app.config.get("TELEGRAM_BOT_USERNAME", "poolcomprasbot")


def _telegram_serializer():
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"])


def _hash_codigo(codigo: str, secret: str) -> str:
    """HMAC-SHA256 — guardamos hash em sess ao, nao o codigo em claro."""
    return hmac.new(secret.encode(), codigo.encode(), hashlib.sha256).hexdigest()


def _iniciar_otp(chat_id) -> bool:
    """Gera codigo de 6 digitos, envia pro chat_id e registra pendencia
    em session. Retorna True se o envio teve sucesso (chat_id valido).

    Se envio falhar (chat_id nao existe, bot bloqueado, etc), nao
    registra pendencia — o usuario recebe feedback e pode tentar outro ID.
    """
    codigo = f"{secrets.randbelow(10**_TELEGRAM_OTP_LEN):0{_TELEGRAM_OTP_LEN}d}"
    secret = current_app.config["SECRET_KEY"]
    codigo_hash = _hash_codigo(codigo, secret)

    # Envia ANTES de salvar pendencia — se falhar, nao contamina session
    class _Pseudo:
        def __init__(self, cid, uid):
            self.telegram_chat_id = str(cid)
            self.id = uid
            self.nome_responsavel = ""
            self.email = ""
    ok = enviar_telegram(
        _Pseudo(chat_id, current_user.id),
        f"<b>PoolCompras — codigo de confirmacao</b>\n\n"
        f"Seu codigo de vinculacao: <code>{codigo}</code>\n\n"
        f"Digite-o no site pra concluir. Expira em 10 minutos.\n"
        f"Se nao solicitou, ignore esta mensagem.",
    )
    if not ok:
        return False

    session["telegram_otp_pendente"] = {
        "chat_id": str(chat_id),
        "codigo_hash": codigo_hash,
        "expira_em": (datetime.now(timezone.utc) +
                      timedelta(seconds=_TELEGRAM_OTP_TTL_SEG)).isoformat(),
    }
    return True


# Campos sensiveis: mudanca exige reautenticacao com senha_atual.
# Redireciona fluxo de pagamento — sem reauth, sessao sequestrada pode
# redirecionar pagamentos pro atacante.
_CAMPOS_SENSIVEIS_FORNECEDOR = ("chave_pix", "banco", "agencia", "conta")
_CAMPOS_SENSIVEIS_LANCHONETE = ("cnpj",)


def _mudou(atual, novo_form):
    """True se novo_form (string) diferir do atual (str/None)."""
    atual_norm = (atual or "").strip()
    return atual_norm != novo_form.strip()


@perfil_bp.route("/", methods=["GET", "POST"])
@login_required
@limiter.limit("20 per hour", methods=["POST"],
               error_message="Muitas atualizacoes de perfil. Aguarde.")
def editar():
    usuario = current_user

    if request.method == "POST":
        senha_atual = request.form.get("senha_atual", "")
        senha_nova = request.form.get("senha_nova", "")
        senha_conf = request.form.get("senha_confirmacao", "")
        # Troca de senha so dispara quando tem senha_nova/confirmacao — senha_atual
        # sozinha eh usada pra autorizar mudanca de campo sensivel sem trocar senha.
        vai_trocar_senha = bool(senha_nova or senha_conf)

        # --- Detectar mudanca em campos sensiveis ---
        mudou_sensivel = False
        if current_user.is_fornecedor and usuario.fornecedor:
            f = usuario.fornecedor
            for campo in _CAMPOS_SENSIVEIS_FORNECEDOR:
                if _mudou(getattr(f, campo), request.form.get(campo, "")):
                    mudou_sensivel = True
                    break
        if current_user.is_lanchonete and usuario.lanchonete:
            l = usuario.lanchonete
            for campo in _CAMPOS_SENSIVEIS_LANCHONETE:
                if _mudou(getattr(l, campo), request.form.get(campo, "")):
                    mudou_sensivel = True
                    break

        # Mudanca de senha OU de campo sensivel exige senha_atual correta.
        if vai_trocar_senha or mudou_sensivel:
            if not check_password_hash(usuario.senha_hash, senha_atual):
                if mudou_sensivel and not vai_trocar_senha:
                    flash("Informe sua senha atual para alterar dados bancários/CNPJ.", "error")
                else:
                    flash("Senha atual incorreta. Nada foi salvo.", "error")
                db.session.rollback()
                return redirect(url_for("perfil.editar"))

        # --- Dados do Usuario (comum aos 3 tipos) ---
        usuario.nome_responsavel = request.form.get("nome_responsavel", "").strip() or usuario.nome_responsavel
        usuario.telefone = request.form.get("telefone", "").strip()
        # telegram_chat_id NAO eh setado aqui — fluxo dedicado /telegram/*
        # garante que apenas o dono do chat pode vincular (via OTP).

        # --- Dados especificos por tipo ---
        if current_user.is_lanchonete and usuario.lanchonete:
            l = usuario.lanchonete
            l.nome_fantasia = request.form.get("nome_fantasia", "").strip() or l.nome_fantasia
            l.cnpj = request.form.get("cnpj", "").strip() or None
            l.endereco = request.form.get("endereco", "").strip()
            l.bairro = request.form.get("bairro", "").strip()
            l.cidade = request.form.get("cidade", "").strip() or "Londrina"
        elif current_user.is_fornecedor and usuario.fornecedor:
            f = usuario.fornecedor
            f.razao_social = request.form.get("razao_social", "").strip() or f.razao_social
            f.nome_contato = request.form.get("nome_contato", "").strip()
            f.telefone = request.form.get("telefone_fornecedor", "").strip() or usuario.telefone
            f.cidade = request.form.get("cidade", "").strip()
            f.chave_pix = request.form.get("chave_pix", "").strip() or None
            f.banco = request.form.get("banco", "").strip() or None
            f.agencia = request.form.get("agencia", "").strip() or None
            f.conta = request.form.get("conta", "").strip() or None
            f.aparece_no_marketplace = "aparece_no_marketplace" in request.form

        # --- Troca de senha (se fluxo iniciado acima, senha_atual ja foi validada) ---
        if vai_trocar_senha:
            if len(senha_nova) < 8:
                flash("A nova senha deve ter pelo menos 8 caracteres.", "error")
                db.session.rollback()
                return redirect(url_for("perfil.editar"))
            if senha_nova != senha_conf:
                flash("As senhas não conferem.", "error")
                db.session.rollback()
                return redirect(url_for("perfil.editar"))
            usuario.senha_hash = generate_password_hash(senha_nova)
            usuario.senha_atualizada_em = datetime.now(timezone.utc).replace(tzinfo=None)
            flash("Perfil atualizado e senha trocada com sucesso.", "success")
        else:
            flash("Perfil atualizado com sucesso.", "success")

        db.session.commit()
        return redirect(url_for("perfil.editar"))

    return render_template("perfil/editar.html", usuario=usuario,
                           bot_username=_bot_username())


# --------- Vinculacao de Telegram via deep link ---------


@perfil_bp.route("/telegram/iniciar", methods=["POST"])
@login_required
@limiter.limit("10 per hour", error_message="Muitas tentativas. Aguarde.")
def telegram_iniciar():
    """Gera token assinado + redireciona pro deep link do bot."""
    token = _telegram_serializer().dumps(current_user.id, salt=_TELEGRAM_SALT)
    deep_link = f"https://t.me/{_bot_username()}?start={token}"
    session["telegram_token"] = token
    return redirect(deep_link)


@perfil_bp.route("/telegram/confirmar", methods=["POST"])
@login_required
@limiter.limit("20 per hour", error_message="Muitas tentativas. Aguarde.")
def telegram_confirmar():
    """Apos /start no bot, busca chat_id via getUpdates + dispara OTP."""
    token_esperado = session.pop("telegram_token", None)
    if not token_esperado:
        flash("Sessao de conexao expirada. Clique 'Conectar Telegram' novamente.", "warning")
        return redirect(url_for("perfil.editar"))

    try:
        user_id = _telegram_serializer().loads(
            token_esperado, salt=_TELEGRAM_SALT, max_age=_TELEGRAM_TTL_SEG,
        )
        if user_id != current_user.id:
            raise BadSignature("token de outro usuario")
    except (BadSignature, SignatureExpired):
        flash("Link de conexao invalido ou expirado. Tente novamente.", "error")
        return redirect(url_for("perfil.editar"))

    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        flash("Bot Telegram nao esta configurado no servidor. Contate o admin.", "error")
        return redirect(url_for("perfil.editar"))

    chat_id = _buscar_chat_id_por_token(bot_token, token_esperado)
    if not chat_id:
        flash(
            "Nao encontramos seu /start no Telegram. Verifique se abriu o bot "
            f"@{_bot_username()} e apertou 'Iniciar' dentro de 10 minutos.",
            "warning",
        )
        return redirect(url_for("perfil.editar"))

    if not _iniciar_otp(chat_id):
        flash("Nao conseguimos enviar o codigo de confirmacao. Tente novamente.", "error")
        return redirect(url_for("perfil.editar"))

    flash(
        "Enviamos um codigo de 6 digitos no seu Telegram — cole-o abaixo pra concluir.",
        "info",
    )
    return redirect(url_for("perfil.telegram_codigo"))


@perfil_bp.route("/telegram/manual", methods=["POST"])
@login_required
@limiter.limit("10 per hour", error_message="Muitas tentativas. Aguarde.")
def telegram_manual():
    """Usuario informa chat_id diretamente (fallback).

    Mesmo com chat_id em maos, exige OTP: se for chat_id alheio, a msg do
    codigo vai pro dono real — atacante nao consegue colar.
    """
    chat_id = request.form.get("chat_id", "").strip()
    if not chat_id or not chat_id.lstrip("-").isdigit():
        flash("chat_id invalido (deve ser numerico).", "error")
        return redirect(url_for("perfil.editar"))

    if not os.environ.get("TELEGRAM_BOT_TOKEN"):
        flash("Bot Telegram nao esta configurado no servidor.", "error")
        return redirect(url_for("perfil.editar"))

    if not _iniciar_otp(chat_id):
        flash(
            "Nao conseguimos enviar o codigo pro chat_id informado. Confirme "
            "que voce iniciou conversa com o bot e digitou o ID correto.",
            "error",
        )
        return redirect(url_for("perfil.editar"))

    flash("Enviamos um codigo de 6 digitos no Telegram — cole-o abaixo.", "info")
    return redirect(url_for("perfil.telegram_codigo"))


@perfil_bp.route("/telegram/codigo", methods=["GET", "POST"])
@login_required
@limiter.limit("20 per hour", methods=["POST"],
               error_message="Muitas tentativas. Aguarde.")
def telegram_codigo():
    """Formulario pra colar o codigo OTP que foi enviado pro Telegram.

    GET: renderiza form. POST: valida codigo + TTL, salva chat_id se bater.
    """
    pendente = session.get("telegram_otp_pendente")
    if not pendente:
        flash("Nenhuma vinculacao pendente. Clique em 'Conectar Telegram' no seu perfil.",
              "warning")
        return redirect(url_for("perfil.editar"))

    # Expirou?
    expira_em = datetime.fromisoformat(pendente["expira_em"])
    if datetime.now(timezone.utc) > expira_em:
        session.pop("telegram_otp_pendente", None)
        flash("Codigo expirado. Clique em 'Conectar Telegram' novamente.", "warning")
        return redirect(url_for("perfil.editar"))

    if request.method == "POST":
        informado = request.form.get("codigo", "").strip()
        if not informado or len(informado) != _TELEGRAM_OTP_LEN or not informado.isdigit():
            flash("Codigo invalido (6 digitos numericos).", "error")
            return render_template("perfil/telegram_codigo.html",
                                    bot_username=_bot_username())

        secret = current_app.config["SECRET_KEY"]
        esperado_hash = pendente["codigo_hash"]
        if not hmac.compare_digest(_hash_codigo(informado, secret), esperado_hash):
            flash("Codigo incorreto. Tente de novo.", "error")
            return render_template("perfil/telegram_codigo.html",
                                    bot_username=_bot_username())

        # OK — confirma vinculacao. Coluna eh BigInteger.
        current_user.telegram_chat_id = int(pendente["chat_id"])
        db.session.commit()
        session.pop("telegram_otp_pendente", None)
        enviar_telegram(
            current_user,
            "<b>Telegram conectado!</b>\n\nA partir de agora voce recebe "
            "notificacoes do PoolCompras aqui. Se quiser desvincular, volte "
            "em Meu perfil -> Desconectar Telegram.",
        )
        flash("Telegram conectado com sucesso!", "success")
        return redirect(url_for("perfil.editar"))

    return render_template("perfil/telegram_codigo.html",
                            bot_username=_bot_username())


@perfil_bp.route("/telegram/desvincular", methods=["POST"])
@login_required
def telegram_desvincular():
    current_user.telegram_chat_id = None
    session.pop("telegram_otp_pendente", None)
    db.session.commit()
    flash("Telegram desconectado. Notificacoes caem no log do servidor.", "info")
    return redirect(url_for("perfil.editar"))


def _buscar_chat_id_por_token(bot_token: str, token: str):
    """Chama getUpdates e procura uma mensagem com '/start <token>'.

    Retorna chat_id (int) se encontrar, None caso contrario.
    Nao levanta excecao — falha eh feedback normal ao usuario.
    """
    url = f"https://api.telegram.org/bot{bot_token}/getUpdates"
    try:
        r = requests.get(url, timeout=8)
        data = r.json() if r.status_code == 200 else {}
    except requests.RequestException as e:
        logger.warning("TELEGRAM_GET_UPDATES_EXC err=%s", e)
        return None

    if not data.get("ok"):
        logger.warning("TELEGRAM_GET_UPDATES_FAIL body=%s", str(data)[:200])
        return None

    alvo = f"/start {token}"
    for upd in data.get("result", []):
        msg = upd.get("message") or {}
        if (msg.get("text") or "").strip() == alvo:
            chat = msg.get("chat") or {}
            if chat.get("id"):
                return chat["id"]
    return None
