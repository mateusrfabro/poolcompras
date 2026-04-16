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

    with app.app_context():
        db.create_all()

    return app
