import os
import secrets
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Base. SECRET_KEY tem fallback aleatorio aqui (overridable por subclasses)."""
    # Em dev, se faltar no env gera uma aleatoria por processo (sessoes resetam ao reiniciar).
    # Producao sobrescreve sem fallback.
    SECRET_KEY = os.getenv("SECRET_KEY") or secrets.token_hex(32)
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL", "sqlite:///poolcompras.db"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # Limite de upload (sera usado quando comprovantes entrarem na Fase 2)
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    DEBUG = False
    # Em producao, SECRET_KEY DEVE vir do ambiente. Sem fallback aceitavel.
    SECRET_KEY = os.getenv("SECRET_KEY")
    # Cookies de sessao seguros quando rodando atras de HTTPS
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"


config = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "default": DevelopmentConfig,
}