import logging
from datetime import datetime, timezone
from urllib.parse import urlparse, urljoin
from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app, session
from flask_login import login_user, logout_user, login_required, current_user
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from sqlalchemy import select
from app.services.passwords import (
    hash_senha, check_senha, check_dummy,
)
from app import db, limiter
from app.models import Usuario, Lanchonete, Fornecedor
from app.services.notificacoes import enviar_link_recuperacao


def _usuario_por_email(email: str) -> Usuario | None:
    """Helper SQLA 2.0 pra buscar Usuario por email (padrao usado em 4 rotas)."""
    return db.session.execute(
        select(Usuario).where(Usuario.email == email)
    ).scalar_one_or_none()


def _proximo_url_seguro(alvo: str | None) -> str | None:
    """Retorna `alvo` se apontar pra mesmo host do app; senao None.

    Protege contra open redirect no ?next= do login. Aceita apenas paths
    relativos ou URLs absolutas com host == request.host.
    """
    if not alvo:
        return None
    ref = urlparse(request.host_url)
    destino = urlparse(urljoin(request.host_url, alvo))
    # So http/https + mesmo host. Bloqueia javascript:, data:, //evil.com etc.
    if destino.scheme in ("http", "https") and destino.netloc == ref.netloc:
        return alvo
    return None

logger = logging.getLogger(__name__)

auth_bp = Blueprint("auth", __name__)


def _client_ip() -> str:
    """IP do cliente atras de Cloudflare Tunnel.

    Prioridade:
    1. CF-Connecting-IP — Cloudflare injeta o IP real, atacante nao consegue forjar
       atras de outro Cloudflare. Esta eh a fonte autoritativa em prod.
    2. X-Forwarded-For — fallback. Confiavel APENAS quando atras de proxy proprio
       (ProxyFix configurado em wsgi). Em prod sem ProxyFix, atacante forja livremente.
    3. request.remote_addr — fallback final.
    """
    cf = request.headers.get("CF-Connecting-IP", "").strip()
    if cf:
        return cf
    xff = request.headers.get("X-Forwarded-For", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.remote_addr or "-"


def _mask_email(email: str) -> str:
    """Mask de email pra log (LGPD): 'mateus@gmail.com' -> 'm***@gmail.com'.

    Mantem dominio (util pra correlacao com domain-based abuse) e 1a letra
    do local (util pra correlacao com mesmo user). Tira o resto.
    """
    if not email or "@" not in email:
        return "?"
    local, dominio = email.split("@", 1)
    inicial = local[0] if local else "?"
    return f"{inicial}***@{dominio}"

# Token de recuperacao de senha — sem tabela extra, assinado com SECRET_KEY
_RECUPERACAO_SALT = "recuperar-senha"
_RECUPERACAO_TTL_SEG = 3600  # 1 hora

# Hash bcrypt dummy usado pra equalizar tempo de resposta em login com
# email inexistente (timing attack). Gerado com generate_password_hash
# — qualquer hash bcrypt serve; conteudo nao eh usado.
_DUMMY_HASH = None  # placeholder retrocompat — Argon2 dummy mora em passwords.check_dummy


def _token_serializer():
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"])


def _agora_naive():
    return datetime.now(timezone.utc)


@auth_bp.route("/login", methods=["GET", "POST"])
@limiter.limit("5 per minute", methods=["POST"],
               error_message="Muitas tentativas de login. Aguarde 1 minuto.")
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        senha = request.form.get("senha", "")

        usuario = _usuario_por_email(email)
        # Equalizar timing: gasta o mesmo custo argon2 mesmo se email nao existe.
        # check_senha tambem retorna novo_hash quando o user tem hash legacy
        # (pbkdf2/scrypt) — fazemos rehash pra Argon2 no proximo login.
        novo_hash = None
        if usuario:
            senha_ok, novo_hash = check_senha(senha, usuario.senha_hash)
        else:
            check_dummy(senha)
            senha_ok = False

        if usuario and senha_ok:
            # Rehash legacy -> Argon2 (transparente pro user).
            if novo_hash:
                usuario.senha_hash = novo_hash
                db.session.commit()
                logger.info("PWD_REHASH_ARGON2 usuario=%s", usuario.id)
            if not getattr(usuario, "ativo", True):
                logger.warning("LOGIN_BLOQUEADO email=%s ip=%s motivo=inativo",
                               _mask_email(email), _client_ip())
                flash("Conta desativada. Contate o administrador.", "error")
                return render_template("auth/login.html", email_anterior=email)
            # Defesa contra session fixation: zera o cookie de sessao antes de
            # autenticar. Cookie que o atacante possa ter plantado eh descartado.
            session.clear()
            login_user(usuario)
            logger.info("LOGIN_OK usuario=%s email=%s tipo=%s ip=%s",
                        usuario.id, _mask_email(email), usuario.tipo, _client_ip())
            # Validacao anti open-redirect: so aceita next apontando pro proprio host.
            proximo = _proximo_url_seguro(request.args.get("next"))
            return redirect(proximo or url_for("main.dashboard"))

        # Nao revela se o email existe ou nao (timing ja equalizado acima)
        logger.warning("LOGIN_FAIL email=%s ip=%s usuario_existe=%s",
                       _mask_email(email), _client_ip(), bool(usuario))
        flash("E-mail ou senha incorretos.", "error")
        # erro_login=True faz o template marcar campos com is-invalid +
        # mostrar field-error embaixo. email_anterior preserva o que digitou.
        return render_template("auth/login.html",
                                erro_login=True, email_anterior=email)

    return render_template("auth/login.html")


@auth_bp.route("/registro", methods=["GET", "POST"])
@limiter.limit("10 per hour", methods=["POST"],
               error_message="Muitos cadastros recentes. Aguarde antes de tentar novamente.")
def registro():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        senha = request.form.get("senha", "")
        nome = request.form.get("nome_responsavel", "").strip()
        telefone = request.form.get("telefone", "").strip()
        nome_fantasia = request.form.get("nome_fantasia", "").strip()
        cnpj = request.form.get("cnpj", "").strip()
        endereco = request.form.get("endereco", "").strip()
        bairro = request.form.get("bairro", "").strip()
        aceite_termos = request.form.get("aceite_termos") == "on"

        if not aceite_termos:
            flash("Voce precisa aceitar os Termos e a Privacidade pra continuar.", "error")
            return render_template(
                "auth/registro.html",
                erro_termos=True,
                form={
                    "email": email, "nome_responsavel": nome, "telefone": telefone,
                    "nome_fantasia": nome_fantasia, "cnpj": cnpj,
                    "endereco": endereco, "bairro": bairro,
                },
            )

        if len(senha) < 8:
            flash("A senha deve ter pelo menos 8 caracteres.", "error")
            return render_template(
                "auth/registro.html",
                erro_senha=True,
                form={
                    "email": email, "nome_responsavel": nome, "telefone": telefone,
                    "nome_fantasia": nome_fantasia, "cnpj": cnpj,
                    "endereco": endereco, "bairro": bairro,
                },
            )

        if _usuario_por_email(email):
            # Nao revela se e-mail existe (anti-enumeration). Em prod com email
            # transacional, o ideal eh enviar mensagem "alguem tentou criar
            # conta com seu email" pro dono real do endereco.
            logger.info("REGISTRO_TENTATIVA_DUPLICADA email=%s ip=%s",
                        _mask_email(email), _client_ip())
            flash("Não foi possível concluir o cadastro. Se você já tem conta, "
                  "faça login. Se esqueceu a senha, use 'Esqueci minha senha'.",
                  "warning")
            return redirect(url_for("auth.login"))

        usuario = Usuario(
            email=email,
            senha_hash=hash_senha(senha),
            nome_responsavel=nome,
            telefone=telefone,
            tipo="lanchonete",
            aceite_termos_em=datetime.now(timezone.utc),
        )
        db.session.add(usuario)
        db.session.flush()

        lanchonete = Lanchonete(
            usuario_id=usuario.id,
            nome_fantasia=nome_fantasia,
            cnpj=cnpj if cnpj else None,
            endereco=endereco,
            bairro=bairro,
        )
        db.session.add(lanchonete)
        db.session.commit()

        session.clear()
        login_user(usuario)
        flash("Cadastro realizado! Bem-vindo ao PoolCompras.", "success")
        return redirect(url_for("main.dashboard"))

    return render_template("auth/registro.html")


@auth_bp.route("/registro/fornecedor", methods=["GET", "POST"])
@limiter.limit("10 per hour", methods=["POST"],
               error_message="Muitos cadastros recentes. Aguarde antes de tentar novamente.")
def registro_fornecedor():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        senha = request.form.get("senha", "")
        nome = request.form.get("nome_responsavel", "").strip()
        telefone = request.form.get("telefone", "").strip()
        razao_social = request.form.get("razao_social", "").strip()
        cidade = request.form.get("cidade", "").strip()
        aceite_termos = request.form.get("aceite_termos") == "on"

        if not aceite_termos:
            flash("Voce precisa aceitar os Termos e a Privacidade pra continuar.", "error")
            return render_template(
                "auth/registro_fornecedor.html",
                erro_termos=True,
                form={
                    "email": email, "nome_responsavel": nome, "telefone": telefone,
                    "razao_social": razao_social, "cidade": cidade,
                },
            )

        if len(senha) < 8:
            flash("A senha deve ter pelo menos 8 caracteres.", "error")
            return render_template(
                "auth/registro_fornecedor.html",
                erro_senha=True,
                form={
                    "email": email, "nome_responsavel": nome, "telefone": telefone,
                    "razao_social": razao_social, "cidade": cidade,
                },
            )

        if _usuario_por_email(email):
            # Anti-enumeration (mesmo padrao do registro lanchonete).
            logger.info("REGISTRO_FORN_TENTATIVA_DUPLICADA email=%s ip=%s",
                        _mask_email(email), _client_ip())
            flash("Não foi possível concluir o cadastro. Se você já tem conta, "
                  "faça login. Se esqueceu a senha, use 'Esqueci minha senha'.",
                  "warning")
            return redirect(url_for("auth.login"))

        usuario = Usuario(
            email=email,
            senha_hash=hash_senha(senha),
            nome_responsavel=nome,
            telefone=telefone,
            tipo="fornecedor",
            aceite_termos_em=datetime.now(timezone.utc),
        )
        db.session.add(usuario)
        db.session.flush()

        fornecedor = Fornecedor(
            usuario_id=usuario.id,
            razao_social=razao_social,
            nome_contato=nome,
            telefone=telefone,
            email=email,
            cidade=cidade,
        )
        db.session.add(fornecedor)
        db.session.commit()

        session.clear()
        login_user(usuario)
        flash("Cadastro realizado! Bem-vindo ao PoolCompras.", "success")
        return redirect(url_for("fornecedor.dashboard"))

    return render_template("auth/registro_fornecedor.html")


@auth_bp.route("/logout", methods=["POST"])
@login_required
def logout():
    """Logout via POST + CSRF token. GET nao funciona (defesa contra
    `<img src="/logout">` derrubando sessao da vitima)."""
    uid = current_user.id
    email = current_user.email
    logout_user()
    session.clear()
    logger.info("LOGOUT usuario=%s email=%s ip=%s", uid, _mask_email(email), _client_ip())
    return redirect(url_for("auth.login"))


@auth_bp.route("/esqueci-senha", methods=["GET", "POST"])
@limiter.limit("5 per hour", methods=["POST"],
               error_message="Muitas tentativas recentes. Aguarde 1 hora.")
def esqueci_senha():
    """Recebe o e-mail, gera token assinado + chama service de notificacao."""
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        usuario = _usuario_por_email(email) if email else None

        # Nao vazamos existencia do e-mail — mensagem identica em qualquer caso.
        if usuario:
            token = _token_serializer().dumps(usuario.id, salt=_RECUPERACAO_SALT)
            link = url_for("auth.redefinir_senha", token=token, _external=True)
            enviar_link_recuperacao(usuario, link)

        flash(
            "Se o e-mail existir no sistema, enviaremos as instruções em instantes.",
            "success",
        )
        return redirect(url_for("auth.login"))

    return render_template("auth/esqueci_senha.html")


@auth_bp.route("/redefinir-senha/<token>", methods=["GET", "POST"])
@limiter.limit("10 per hour", methods=["POST"],
               error_message="Muitas tentativas recentes. Aguarde 1 hora.")
def redefinir_senha(token):
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    try:
        user_id, token_emitido_em = _token_serializer().loads(
            token, salt=_RECUPERACAO_SALT, max_age=_RECUPERACAO_TTL_SEG,
            return_timestamp=True,
        )
    except SignatureExpired:
        flash("Link expirado. Gere um novo em 'Esqueci minha senha'.", "error")
        return redirect(url_for("auth.esqueci_senha"))
    except BadSignature:
        flash("Link inválido.", "error")
        return redirect(url_for("auth.esqueci_senha"))

    usuario = db.session.get(Usuario, user_id)
    if not usuario:
        flash("Usuário não encontrado.", "error")
        return redirect(url_for("auth.esqueci_senha"))

    # Token one-use: se o usuario ja trocou senha DEPOIS deste token ser
    # emitido, recusar. Invalida link reusado (log, historico, proxy).
    if usuario.senha_atualizada_em:
        emitido_naive = token_emitido_em.replace(tzinfo=None)
        if usuario.senha_atualizada_em >= emitido_naive:
            flash("Este link já foi utilizado. Gere um novo se precisar.", "error")
            return redirect(url_for("auth.esqueci_senha"))

    if request.method == "POST":
        senha = request.form.get("senha", "")
        confirmacao = request.form.get("confirmacao", "")
        if len(senha) < 8:
            flash("A senha deve ter pelo menos 8 caracteres.", "error")
            return render_template("auth/redefinir_senha.html",
                                    token=token, erro_senha_curta=True)
        if senha != confirmacao:
            flash("As senhas não conferem.", "error")
            return render_template("auth/redefinir_senha.html",
                                    token=token, erro_match=True)

        usuario.senha_hash = hash_senha(senha)
        usuario.senha_atualizada_em = _agora_naive()
        db.session.commit()
        flash("Senha redefinida com sucesso. Faça login com a nova senha.", "success")
        return redirect(url_for("auth.login"))

    return render_template("auth/redefinir_senha.html", token=token)
