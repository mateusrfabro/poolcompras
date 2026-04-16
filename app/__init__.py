from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from config import config

db = SQLAlchemy()
login_manager = LoginManager()
login_manager.login_view = "auth.login"
login_manager.login_message = "Faça login para acessar o sistema."


def create_app(config_name="default"):
    app = Flask(__name__)
    app.config.from_object(config[config_name])

    db.init_app(app)
    login_manager.init_app(app)

    from app.routes.auth import auth_bp
    from app.routes.main import main_bp
    from app.routes.pedidos import pedidos_bp
    from app.routes.rodadas import rodadas_bp
    from app.routes.admin import admin_bp
    from app.routes.fornecedor import fornecedor_bp
    from app.routes.historico import historico_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(pedidos_bp)
    app.register_blueprint(rodadas_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(fornecedor_bp)
    app.register_blueprint(historico_bp)

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

    with app.app_context():
        db.create_all()

    return app
