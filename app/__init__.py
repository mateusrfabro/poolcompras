from flask import Flask, request
from werkzeug.middleware.proxy_fix import ProxyFix
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from flask_migrate import Migrate
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_talisman import Talisman
from flask_caching import Cache
from config import config


def _ip_real_atras_cloudflare() -> str:
    """Key func do Flask-Limiter ciente de Cloudflare Tunnel.

    Prioriza CF-Connecting-IP (autoritativo, atacante nao consegue forjar
    atras de outro Cloudflare). Fallback: X-Forwarded-For -> remote_addr.
    Sem isso, rate-limit ficaria preso ao IP do tunnel (nao do user real).
    """
    cf = request.headers.get("CF-Connecting-IP", "").strip()
    if cf:
        return cf
    return get_remote_address()

db = SQLAlchemy()
login_manager = LoginManager()
login_manager.login_view = "auth.login"
login_manager.login_message = "Faça login para acessar o sistema."
# session_protection=strong regenera _id da sessao quando detecta troca de
# user-agent/IP e descarta sessao nao autenticada. Camada extra contra
# session fixation (alem do session.clear() explicito no login).
login_manager.session_protection = "strong"
csrf = CSRFProtect()
migrate = Migrate()
# Rate-limiter: chave = IP do cliente. Backend definido em config (memory:// em
# dev/test; redis://redis:6379/0 em prod via docker-compose).
# key_func usa CF-Connecting-IP quando atras de Cloudflare Tunnel.
limiter = Limiter(key_func=_ip_real_atras_cloudflare, default_limits=["200 per hour"])
# Cache de KPIs do dashboard admin (TTL 30s). SimpleCache em dev/single-worker;
# NullCache em testing pra cada teste pegar dado fresco; Redis em prod multi-worker
# (config futura).
cache = Cache()


def create_app(config_name="default"):
    app = Flask(__name__)
    app.config.from_object(config[config_name])

    # ProxyFix em prod: atras de Cloudflare Tunnel, request.remote_addr eh
    # SEMPRE o IP do tunnel container, nunca do cliente. Sem ProxyFix nao
    # adianta ler X-Forwarded-For — Werkzeug ignora headers fakes do remote.
    # x_for=1 = confia em UM hop de proxy (o cloudflared rodando no Yggdrasil).
    if config_name == "production":
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    # Em producao, SECRET_KEY tem que vir do ambiente. Sem fallback.
    if config_name == "production" and not app.config.get("SECRET_KEY"):
        raise RuntimeError(
            "SECRET_KEY nao configurada em producao. "
            "Defina no .env ou variavel de ambiente antes de iniciar."
        )

    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    # Importa models antes do migrate.init_app para o autogenerate enxergar tudo
    from app import models  # noqa: F401
    migrate.init_app(app, db, render_as_batch=True)  # batch=True para SQLite ALTER COLUMN
    limiter.init_app(app)
    cache.init_app(app)

    # Headers de seguranca (Talisman).
    # CSP permissivo para inline styles (templates atuais tem style=""). Tighten no futuro.
    # force_https=False em dev; ligado via config em producao.
    csp = {
        "default-src": "'self'",
        # Google Fonts: CSS em fonts.googleapis.com, .woff2 em fonts.gstatic.com.
        "style-src": ["'self'", "'unsafe-inline'", "https://fonts.googleapis.com"],
        "script-src": "'self'",
        "img-src": ["'self'", "data:"],
        "font-src": ["'self'", "https://fonts.gstatic.com"],
        "object-src": "'none'",
        "base-uri": "'self'",
        "form-action": "'self'",
        "frame-ancestors": "'none'",
    }
    # Permissions-Policy: nega features de browser que o app nao usa.
    # Defesa em profundidade — XSS futuro nao consegue acessar camera/mic/etc.
    permissions_policy = {
        "accelerometer":     "()",
        "camera":            "()",
        "geolocation":       "()",
        "gyroscope":         "()",
        "magnetometer":      "()",
        "microphone":        "()",
        "payment":           "()",
        "usb":               "()",
        "interest-cohort":   "()",  # Floc/Topics opt-out
    }
    Talisman(
        app,
        content_security_policy=csp,
        content_security_policy_nonce_in=None,
        force_https=(config_name == "production"),
        strict_transport_security=(config_name == "production"),
        strict_transport_security_max_age=31536000,  # 1 ano
        referrer_policy="strict-origin-when-cross-origin",
        frame_options="DENY",
        session_cookie_secure=(config_name == "production"),
        permissions_policy=permissions_policy,
    )

    # Storage de uploads (comprovantes etc.). Implementacao local agora; trocar por S3 no futuro.
    from app.services.storage import init_storage
    init_storage(app)

    from app.routes.auth import auth_bp
    from app.routes.main import main_bp
    from app.routes.pedidos import pedidos_bp
    from app.routes.rodadas import rodadas_bp
    from app.routes.admin import admin_bp
    from app.routes.fornecedor import fornecedor_bp
    from app.routes.historico import historico_bp
    from app.routes.uploads import uploads_bp
    from app.routes.fluxo import fluxo_bp
    from app.routes.perfil import perfil_bp
    from app.routes.marketplace import marketplace_bp
    from app.routes.telegram_webhook import telegram_webhook_bp
    from app.cli import cron_bp
    from app.cli_telegram import telegram_cli_bp

    # Error handlers amigaveis
    import logging as _logging
    import re as _re
    from flask import render_template, request, jsonify, redirect, url_for, flash
    from flask_login import current_user
    _err_logger = _logging.getLogger("app.errors")

    # Mascara tokens em access logs (Werkzeug + Gunicorn). Sem isso, paths
    # como /redefinir-senha/<token>, /webhook/telegram/<secret> e
    # /uploads/<key> caem em texto-claro nos logs — qualquer um que ler o
    # log file recupera a sessao/segredo.
    _TOKEN_PATH_RE = _re.compile(
        r'(/(?:redefinir-senha|webhook/telegram|uploads)/)([^/?\s"\']+)'
    )

    class _SanitizeTokenFilter(_logging.Filter):
        def filter(self, record):
            try:
                msg = record.getMessage()
            except Exception:
                return True
            if isinstance(msg, str) and "/" in msg:
                novo = _TOKEN_PATH_RE.sub(r"\1<redacted>", msg)
                if novo != msg:
                    record.msg = novo
                    record.args = ()
            return True

    _sanitize_filter = _SanitizeTokenFilter()
    for _name in ("werkzeug", "gunicorn.access", "gunicorn.error"):
        _logging.getLogger(_name).addFilter(_sanitize_filter)

    @app.errorhandler(404)
    def erro_404(e):
        return render_template("errors/404.html"), 404

    @app.errorhandler(403)
    def erro_403(e):
        return render_template("errors/403.html"), 403

    @app.errorhandler(413)
    def erro_413(e):
        # Upload maior que MAX_CONTENT_LENGTH (5MB hoje). Pra AJAX retorna
        # JSON pra fetch tratar; pra request comum cai num template generico.
        wants_json = (
            request.is_json
            or "application/json" in (request.headers.get("Accept") or "")
            or request.headers.get("X-Requested-With") == "XMLHttpRequest"
        )
        if wants_json:
            return jsonify({"erro": "arquivo_muito_grande",
                            "limite_mb": 5}), 413
        flash("Arquivo muito grande. Tamanho maximo: 5 MB.", "error")
        # Volta pra referer ou home; sem template dedicado pra evitar churn.
        # 303 forca GET no destino (POST -> GET seguro apos erro).
        return redirect(request.referrer or url_for("main.index"), code=303)

    @app.errorhandler(500)
    def erro_500(e):
        # logger.exception captura traceback completo — sem isso, falha
        # silenciosa em prod (saber QUE deu 500 nao basta; precisa do stack).
        uid = getattr(current_user, "id", None) if current_user else None
        _err_logger.exception(
            "UNHANDLED_500 path=%s method=%s usuario=%s",
            request.path, request.method, uid,
        )
        db.session.rollback()
        return render_template("errors/500.html"), 500

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(pedidos_bp)
    app.register_blueprint(rodadas_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(fornecedor_bp)
    app.register_blueprint(historico_bp)
    app.register_blueprint(uploads_bp)
    app.register_blueprint(fluxo_bp)
    app.register_blueprint(perfil_bp)
    app.register_blueprint(marketplace_bp)
    # Webhook do Telegram — POST externo, sem CSRF (seguranca via secret na URL)
    csrf.exempt(telegram_webhook_bp)
    app.register_blueprint(telegram_webhook_bp)
    app.register_blueprint(cron_bp)
    app.register_blueprint(telegram_cli_bp)

    # Pluralizacao por unidade. Simbolos (kg, g, ml, l) sao invariaveis em PT-BR.
    PLURAIS = {
        "unidade": "unidades",
        "caixa":   "caixas",
        "fardo":   "fardos",
        "pacote":  "pacotes",
        "litro":   "litros",
        "quilo":   "quilos",
        "saco":    "sacos",
        "balde":   "baldes",
        # Simbolos invariaveis
        "kg": "kg", "g": "g", "ml": "ml", "l": "l",
    }

    # Filter: formata quantidade removendo .0 quando inteira (ex: 5.0 -> "5", 11.7 -> "11,7")
    @app.template_filter("qtd")
    def format_quantidade(valor):
        if valor is None:
            return "-"
        try:
            v = float(valor)
        except (TypeError, ValueError):
            return str(valor)
        if v == int(v):
            return str(int(v))
        return f"{v:.1f}".replace(".", ",")

    # Filter: formata valor monetario em BRL (R$ 1.234,56)
    @app.template_filter("brl")
    def format_brl(valor):
        if valor is None:
            return "—"
        try:
            v = float(valor)
        except (TypeError, ValueError):
            return str(valor)
        # 1234.5 -> "1.234,50"
        inteiro, decimal = f"{v:.2f}".split(".")
        sinal = "-" if inteiro.startswith("-") else ""
        inteiro = inteiro.lstrip("-")
        # Insere separador de milhar
        with_sep = ""
        for i, ch in enumerate(reversed(inteiro)):
            if i and i % 3 == 0:
                with_sep = "." + with_sep
            with_sep = ch + with_sep
        return f"R$ {sinal}{with_sep},{decimal}"

    # Filter: traduz status interno do banco em label PT-BR profissional para exibicao
    STATUS_LABELS = {
        "preparando":           "Preparando catálogo",
        "aguardando_cotacao":   "Aguardando cotação",
        "aguardando_aprovacao": "Aguardando aprovação",
        "aberta":               "Em aberto",
        "fechada":              "Fechada",
        "cotando":              "Em cotação",
        "em_negociacao":        "Em negociação",
        "finalizada":           "Finalizada",
        "cancelada":            "Cancelada",
    }

    @app.template_filter("status_label")
    def status_label(status):
        return STATUS_LABELS.get((status or "").lower(), status or "—")

    # Filter: formata 'qtd unidade' com pluralizacao PT-BR.
    # Ex: 1 + fardo -> '1 fardo'; 5 + fardo -> '5 fardos'; 10.5 + kg -> '10,5 kg'.
    @app.template_filter("fmt_un")
    def format_qtd_unidade(qtd, unidade):
        if qtd is None:
            return "-"
        try:
            v = float(qtd)
        except (TypeError, ValueError):
            return f"{qtd} {unidade}"

        num = format_quantidade(v)
        if not unidade:
            return num
        # Singular se quantidade for exatamente 1; plural caso contrario
        if abs(v - 1.0) < 1e-9:
            un_fmt = unidade
        else:
            un_fmt = PLURAIS.get(unidade.lower(), unidade + "s")
        return f"{num} {un_fmt}"

    def _normaliza_alvo(data):
        """Converte date/datetime pro alvo efetivo. Se datetime com hora 00:00, trata como fim do dia.

        SQLite retorna datetime naive mesmo com DateTime(timezone=True); Postgres retorna aware.
        Pra filtros funcionarem igual nos dois, forca tz UTC se vier naive.
        """
        from datetime import datetime, date, time as dtime, timezone
        if data is None:
            return None
        if isinstance(data, datetime):
            alvo = data
            if alvo.time() == dtime(0, 0):
                alvo = alvo.replace(hour=23, minute=59)
        elif isinstance(data, date):
            alvo = datetime.combine(data, dtime(23, 59))
        else:
            return None
        if alvo.tzinfo is None:
            alvo = alvo.replace(tzinfo=timezone.utc)
        return alvo

    # Filter: tempo restante humanizado ("Fecha em 3h45min", "Fecha em 2 dias", "Encerrada")
    @app.template_filter("countdown")
    def format_countdown(data):
        from datetime import datetime, timezone
        alvo = _normaliza_alvo(data)
        if alvo is None:
            return "—"
        delta = alvo - datetime.now(timezone.utc)
        total_seg = int(delta.total_seconds())
        if total_seg <= 0:
            return "Encerrada"
        dias = total_seg // 86400
        horas = (total_seg % 86400) // 3600
        minutos = (total_seg % 3600) // 60
        if dias >= 2:
            return f"Fecha em {dias} dias"
        if dias == 1:
            return f"Fecha em 1 dia e {horas}h"
        if horas >= 1:
            return f"Fecha em {horas}h{minutos:02d}min"
        return f"Fecha em {minutos}min"

    # Filter: formata data+hora em PT-BR ("18/04/2026 as 23:59")
    @app.template_filter("datetime_br")
    def format_datetime_br(data):
        alvo = _normaliza_alvo(data)
        if alvo is None:
            return "—"
        return alvo.strftime("%d/%m/%Y às %H:%M")

    # Filter: formata so a data em PT-BR ("18/04/2026"). Usar em listagens.
    @app.template_filter("data_br")
    def format_data_br(data):
        from datetime import date, datetime as dt
        if data is None:
            return "—"
        if isinstance(data, dt):
            return data.strftime("%d/%m/%Y")
        if isinstance(data, date):
            return data.strftime("%d/%m/%Y")
        return "—"

    # Filter: booleano de urgencia (prazo hoje ou amanha)
    @app.template_filter("urgente")
    def is_urgente(data):
        from datetime import datetime, timezone
        alvo = _normaliza_alvo(data)
        if alvo is None:
            return False
        delta = alvo - datetime.now(timezone.utc)
        return 0 < delta.total_seconds() <= 86400  # <= 24h

    # Filter: traduz EventoRodada.tipo para rotulo PT-BR pra timeline.
    # Nao emojificado (identidade visual do projeto usa texto puro).
    EVENTO_LABELS = {
        "pedido_enviado":         ("Pedido enviado pra moderação", "info"),
        "rodada_fechada":         ("Rodada fechada pelo admin", "info"),
        "cotacao_enviada":        ("Cotação enviada", "info"),
        "proposta_consolidada":   ("Proposta consolidada", "info"),
        "proposta_aceita":        ("Proposta aceita pela lanchonete", "ok"),
        "proposta_recusada":      ("Proposta recusada pela lanchonete", "problema"),
        "comprovante_enviado":    ("Comprovante de pagamento enviado", "ok"),
        "pagamento_confirmado":   ("Pagamento confirmado pelo fornecedor", "ok"),
        "entrega_informada":      ("Entrega informada pelo fornecedor", "ok"),
        "recebimento_confirmado": ("Recebimento confirmado pela lanchonete", "ok"),
        "recebimento_problema":   ("Problema no recebimento", "problema"),
        "avaliacao_enviada":      ("Avaliação enviada", "ok"),
        "rodada_finalizada":      ("Rodada finalizada pelo admin", "ok"),
        "rodada_cancelada":       ("Rodada cancelada pelo admin", "problema"),
        "rodada_em_negociacao":   ("Rodada entrou em negociação", "info"),
        "deadline_vencido":       ("Deadline vencido", "problema"),
    }

    @app.template_filter("evento_label")
    def evento_label(tipo):
        """Converte EventoRodada.tipo -> label amigavel. Desconhecidos: mostra tipo cru."""
        label, _ = EVENTO_LABELS.get(tipo, (tipo.replace("_", " ").capitalize(), "info"))
        return label

    @app.template_filter("evento_status")
    def evento_status(tipo):
        """Converte EventoRodada.tipo -> classe css ('ok' | 'problema' | 'info')."""
        _, status = EVENTO_LABELS.get(tipo, (tipo, "info"))
        return status

    return app
