"""
Entrypoint da aplicacao.

USO LOCAL (dev): `python run.py` -> sobe Flask dev server na porta 5050 com debug.
USO PRODUCAO: usar gunicorn (ver entrypoint.sh / docker-compose). NUNCA `python run.py`
em producao - Werkzeug debugger ativo expoe console RCE.
"""
import os
from app import create_app

env = os.getenv("FLASK_ENV", "development")
config_name = "production" if env == "production" else "development"
app = create_app(config_name)


if __name__ == "__main__":
    # Bloqueia execucao direta com FLASK_ENV=production. Forca uso do gunicorn.
    if env == "production":
        raise SystemExit(
            "Nao execute 'python run.py' com FLASK_ENV=production. "
            "Use gunicorn (ver entrypoint.sh)."
        )
    debug = os.getenv("FLASK_DEBUG", "1") == "1"
    port = int(os.getenv("PORT", "5050"))
    app.run(debug=debug, port=port, host="127.0.0.1")
