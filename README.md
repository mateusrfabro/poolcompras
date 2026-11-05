# Aggron (poolcompras)

Central de compras cooperativa para hamburguerias: as lanchonetes fazem pedidos, o sistema agrega o volume e os
administradores cotam com fornecedores. Volume agregado, preco menor.

Flask + SQLAlchemy + Alembic + Jinja2, CSS e JS vanilla (CSP-safe), PostgreSQL em producao, Docker.

## Estado (05/11/2026)

MVP completo, parado desde 28/05/2026; o socio atua como PO. Guia de deploy em [`DEPLOY.md`](DEPLOY.md) e
convencoes do projeto em [`CLAUDE.md`](CLAUDE.md).

## Rodar localmente

```bash
python -m venv .venv && . .venv/bin/activate   # no Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                            # preencher SECRET_KEY
python run.py                                   # porta 5050
python -m pytest tests/ -q
```

## Licenca

Codigo sob licenca MIT (ver `LICENSE`).
