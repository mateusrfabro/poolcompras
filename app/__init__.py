from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from flask_migrate import Migrate
from config import config

db = SQLAlchemy()
login_manager = LoginManager()
login_manager.login_view = "auth.login"
login_manager.login_message = "Faça login para acessar o sistema."
csrf = CSRFProtect()
migrate = Migrate()


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

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(pedidos_bp)
    app.register_blueprint(rodadas_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(fornecedor_bp)
    app.register_blueprint(historico_bp)
    app.register_blueprint(uploads_bp)
    app.register_blueprint(fluxo_bp)

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
        "aberta":     "Em aberto",
        "fechada":    "Fechada",
        "cotando":    "Em cotação",
        "finalizada": "Finalizada",
        "cancelada":  "Cancelada",
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

    return app
