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
    # Username do bot Telegram (usado pra montar deep link t.me/<username>?start=...)
    TELEGRAM_BOT_USERNAME = os.getenv("TELEGRAM_BOT_USERNAME", "poolcomprasbot")

    # Flask-Caching: SimpleCache eh in-memory por processo. Suficiente pra
    # single-worker (gunicorn -w 1) ou pra dev. Em multi-worker usar Redis.
    CACHE_TYPE = "SimpleCache"
    CACHE_DEFAULT_TIMEOUT = 30  # 30s — KPIs do dashboard admin


class DevelopmentConfig(Config):
    DEBUG = True


class TestingConfig(Config):
    """Configuracao para suite de testes pytest.

    NUNCA toca o DB de desenvolvimento: le TEST_DATABASE_URL (setada pelo conftest),
    com fallback para SQLite in-memory. Se por qualquer motivo o conftest falhar
    em setar, cai em :memory: (nao danifica o arquivo real).
    """
    TESTING = True
    DEBUG = False
    SQLALCHEMY_DATABASE_URI = os.getenv("TEST_DATABASE_URL") or "sqlite:///:memory:"
    WTF_CSRF_ENABLED = False
    SECRET_KEY = "test-secret-never-use-in-prod"
    # NullCache em testes: cada teste lê dado fresco do DB sem interferência
    # de cache de teste anterior. Importantissimo pra evitar flakiness.
    CACHE_TYPE = "NullCache"


class ProductionConfig(Config):
    DEBUG = False
    # Em producao, SECRET_KEY DEVE vir do ambiente. Sem fallback aceitavel.
    SECRET_KEY = os.getenv("SECRET_KEY")
    # Cookies de sessao seguros quando rodando atras de HTTPS
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    # Hardening preventivo pra remember-me caso Flask-Login ative no futuro.
    REMEMBER_COOKIE_SECURE = True
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = "Lax"
    # Pool de conexoes Postgres pra prod atras de pgbouncer/HAProxy.
    # pool_pre_ping: testa conexao antes de usar (descarta a que pgbouncer
    #   matou em idle). pool_recycle: 5min — alinha com pgbouncer default.
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 300,
        "pool_size": 5,
        "max_overflow": 10,
    }


config = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
    "default": DevelopmentConfig,
}