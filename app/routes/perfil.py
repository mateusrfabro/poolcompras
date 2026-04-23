"""Edicao de perfil: o proprio usuario corrige seus dados cadastrais + senha.

Regras:
- Email eh readonly (troca de e-mail eh feature separada por nao ser trivial)
- CNPJ da lanchonete: editavel (erros de cadastro precisam ser corrigidos por ela)
- Troca de senha eh opcional: se senha_nova vazia, nao altera
- Troca de senha exige senha_atual correta (protege de sessao sequestrada)
"""
import logging
import os
from datetime import datetime, timezone

import requests
from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app
from flask_login import login_required, current_user
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from werkzeug.security import check_password_hash, generate_password_hash

from app import db, limiter
from app.services.notificacoes import enviar_telegram

logger = logging.getLogger(__name__)

perfil_bp = Blueprint("perfil", __name__, url_prefix="/perfil")

# Vinculacao Telegram: token assinado embutido no deep link do bot.
# Usuario clica "Conectar Telegram" -> abrimos t.me/<bot>?start=<token>.
# Quando ele manda /start <token> pro bot, chamamos getUpdates, procuramos
# pelo token, extraimos chat_id e salvamos.
_TELEGRAM_SALT = "vincular-telegram"
_TELEGRAM_TTL_SEG = 600  # 10 min — tempo suficiente pra abrir Telegram e clicar start
_TELEGRAM_BOT_USERNAME = "poolcomprasbot"


def _telegram_serializer():
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"])


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
        # Telegram chat_id: opcional, string vazia vira None
        chat_id_raw = request.form.get("telegram_chat_id", "").strip()
        usuario.telegram_chat_id = chat_id_raw or None

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
                           bot_username=_TELEGRAM_BOT_USERNAME)


# --------- Vinculacao de Telegram via deep link ---------


@perfil_bp.route("/telegram/iniciar", methods=["POST"])
@login_required
@limiter.limit("10 per hour", error_message="Muitas tentativas. Aguarde.")
def telegram_iniciar():
    """Gera token assinado + redireciona pro deep link do bot.

    Usuario vai abrir o Telegram com /start <token>. Depois volta e clica
    'Concluir conexao' que chama /telegram/confirmar.
    """
    token = _telegram_serializer().dumps(current_user.id, salt=_TELEGRAM_SALT)
    deep_link = f"https://t.me/{_TELEGRAM_BOT_USERNAME}?start={token}"
    # Guardamos o token na session pra /confirmar saber o que procurar
    from flask import session
    session["telegram_token"] = token
    return redirect(deep_link)


@perfil_bp.route("/telegram/confirmar", methods=["POST"])
@login_required
@limiter.limit("20 per hour", error_message="Muitas tentativas. Aguarde.")
def telegram_confirmar():
    """Apos o usuario ter dado /start no bot, chama getUpdates pra descobrir
    o chat_id dele via match do token assinado.

    Se encontrar: salva chat_id + envia mensagem de confirmacao.
    Senao: flash orienta ir no @userinfobot ou tentar de novo.
    """
    from flask import session
    token_esperado = session.pop("telegram_token", None)
    if not token_esperado:
        flash("Sessao de conexao expirada. Clique 'Conectar Telegram' novamente.", "warning")
        return redirect(url_for("perfil.editar"))

    # Valida que token ainda pertence a este user + nao expirou
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
            "@poolcomprasbot e apertou 'Iniciar' dentro de 10 minutos. "
            "Se preferir, cole o chat_id manualmente abaixo.",
            "warning",
        )
        return redirect(url_for("perfil.editar"))

    # Salva + manda mensagem de confirmacao
    current_user.telegram_chat_id = str(chat_id)
    db.session.commit()
    enviar_telegram(
        current_user,
        "<b>Telegram conectado!</b>\n\nA partir de agora voce recebe "
        "notificacoes do PoolCompras aqui. Se quiser desvincular, volte em "
        "Meu perfil → Desconectar Telegram.",
    )
    flash("Telegram conectado! Voce deve ter recebido uma mensagem de confirmacao.", "success")
    return redirect(url_for("perfil.editar"))


@perfil_bp.route("/telegram/desvincular", methods=["POST"])
@login_required
def telegram_desvincular():
    current_user.telegram_chat_id = None
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
