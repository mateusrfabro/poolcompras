from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from flask_migrate import Migrate
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_talisman import Talisman
from config import config

db = SQLAlchemy()
login_manager = LoginManager()
login_manager.login_view = "auth.login"
login_manager.login_message = "Faça login para acessar o sistema."
csrf = CSRFProtect()
migrate = Migrate()
# Rate-limiter: chave = IP do cliente; backend padrao em memoria (suficiente para
# single-process; para multiplos workers usar Redis no futuro).
limiter = Limiter(key_func=get_remote_address, default_limits=["200 per hour"])


def create_app(config_name="default"):
    app = Flask(__name__)
    app.config.from_object(config[config_name])

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

    # Headers de seguranca (Talisman).
    # CSP permissivo para inline styles (templates atuais tem style=""). Tighten no futuro.
    # force_https=False em dev; ligado via config em producao.
    csp = {
        "default-src": "'self'",
        "style-src": ["'self'", "'unsafe-inline'"],  # alguns templates usam style=""
        "script-src": "'self'",
        "img-src": ["'self'", "data:"],
        "font-src": "'self'",
        "object-src": "'none'",
        "base-uri": "'self'",
        "form-action": "'self'",
        "frame-ancestors": "'none'",
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
    from app.cli import cron_bp

    # Error handlers amigaveis
    from flask import render_template
    @app.errorhandler(404)
    def erro_404(e):
        return render_template("errors/404.html"), 404

    @app.errorhandler(403)
    def erro_403(e):
        return render_template("errors/403.html"), 403

    @app.errorhandler(500)
    def erro_500(e):
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
    app.register_blueprint(cron_bp)

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
        """Converte date/datetime pro alvo efetivo. Se datetime com hora 00:00, trata como fim do dia."""
        from datetime import datetime, date, time as dtime
        if data is None:
            return None
        if isinstance(data, datetime):
            # Se hora 00:00:00, assumir fim do dia (23:59)
            if data.time() == dtime(0, 0):
                return data.replace(hour=23, minute=59)
            return data
        if isinstance(data, date):
            return datetime.combine(data, dtime(23, 59))
        return None

    # Filter: tempo restante humanizado ("Fecha em 3h45min", "Fecha em 2 dias", "Encerrada")
    @app.template_filter("countdown")
    def format_countdown(data):
        from datetime import datetime, timezone
        alvo = _normaliza_alvo(data)
        if alvo is None:
            return "—"
        delta = alvo - datetime.now(timezone.utc).replace(tzinfo=None)
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

    # Filter: booleano de urgencia (prazo hoje ou amanha)
    @app.template_filter("urgente")
    def is_urgente(data):
        from datetime import datetime, timezone
        alvo = _normaliza_alvo(data)
        if alvo is None:
            return False
        delta = alvo - datetime.now(timezone.utc).replace(tzinfo=None)
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
