from datetime import datetime, timezone
from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app
from flask_login import login_user, logout_user, login_required, current_user
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from werkzeug.security import generate_password_hash, check_password_hash
from app import db, limiter
from app.models import Usuario, Lanchonete, Fornecedor
from app.services.notificacoes import enviar_link_recuperacao

auth_bp = Blueprint("auth", __name__)

# Token de recuperacao de senha — sem tabela extra, assinado com SECRET_KEY
_RECUPERACAO_SALT = "recuperar-senha"
_RECUPERACAO_TTL_SEG = 3600  # 1 hora

# Hash bcrypt dummy usado pra equalizar tempo de resposta em login com
# email inexistente (timing attack). Gerado com generate_password_hash
# — qualquer hash bcrypt serve; conteudo nao eh usado.
_DUMMY_HASH = generate_password_hash("dummy-password-never-matches")


def _token_serializer():
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"])


def _agora_naive():
    return datetime.now(timezone.utc).replace(tzinfo=None)


@auth_bp.route("/login", methods=["GET", "POST"])
@limiter.limit("5 per minute", methods=["POST"],
               error_message="Muitas tentativas de login. Aguarde 1 minuto.")
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        senha = request.form.get("senha", "")

        usuario = Usuario.query.filter_by(email=email).first()
        # Equalizar tempo de resposta: mesmo quando o email nao existe,
        # faz check_password_hash contra hash dummy pra nao vazar existencia
        # via timing (bcrypt eh o grosso do custo).
        if usuario:
            senha_ok = check_password_hash(usuario.senha_hash, senha)
        else:
            check_password_hash(_DUMMY_HASH, senha)
            senha_ok = False

        if usuario and senha_ok:
            login_user(usuario)
            next_page = request.args.get("next")
            return redirect(next_page or url_for("main.dashboard"))

        flash("E-mail ou senha incorretos.", "error")

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

        if len(senha) < 8:
            flash("A senha deve ter pelo menos 8 caracteres.", "error")
            return render_template("auth/registro.html")

        if Usuario.query.filter_by(email=email).first():
            flash("Este e-mail já está cadastrado.", "error")
            return render_template("auth/registro.html")

        usuario = Usuario(
            email=email,
            senha_hash=generate_password_hash(senha),
            nome_responsavel=nome,
            telefone=telefone,
            tipo="lanchonete",
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

        if len(senha) < 8:
            flash("A senha deve ter pelo menos 8 caracteres.", "error")
            return render_template("auth/registro_fornecedor.html")

        if Usuario.query.filter_by(email=email).first():
            flash("Este e-mail já está cadastrado.", "error")
            return render_template("auth/registro_fornecedor.html")

        usuario = Usuario(
            email=email,
            senha_hash=generate_password_hash(senha),
            nome_responsavel=nome,
            telefone=telefone,
            tipo="fornecedor",
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

        login_user(usuario)
        flash("Cadastro realizado! Bem-vindo ao PoolCompras.", "success")
        return redirect(url_for("fornecedor.dashboard"))

    return render_template("auth/registro_fornecedor.html")


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
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
        usuario = Usuario.query.filter_by(email=email).first() if email else None

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
            return render_template("auth/redefinir_senha.html", token=token)
        if senha != confirmacao:
            flash("As senhas não conferem.", "error")
            return render_template("auth/redefinir_senha.html", token=token)

        usuario.senha_hash = generate_password_hash(senha)
        usuario.senha_atualizada_em = _agora_naive()
        db.session.commit()
        flash("Senha redefinida com sucesso. Faça login com a nova senha.", "success")
        return redirect(url_for("auth.login"))

    return render_template("auth/redefinir_senha.html", token=token)
