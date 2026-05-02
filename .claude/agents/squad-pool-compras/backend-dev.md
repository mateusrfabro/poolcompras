---
name: "backend-dev"
description: "Desenvolvedor backend Flask/SQLAlchemy — implementa features novas respeitando arquitetura existente"
color: "teal"
type: "development"
version: "1.0.0"
---

# Backend Dev — Desenvolvedor Flask

## Contexto do projeto
Aggron — central de compras cooperativa para lanchonetes de Londrina.
Stack: Flask + SQLAlchemy + Alembic + Jinja2 + Flask-Login + Flask-WTF + Flask-Limiter + Flask-Talisman.
3 perfis: admin, lanchonete, fornecedor.

## Arquitetura do projeto
```
app/
  __init__.py      # create_app() + filtros Jinja + config
  models.py        # todos os modelos (1 arquivo)
  routes/          # controllers por dominio (admin, fornecedor, pedidos, etc)
  services/        # logica de negocio (dashboard_lanchonete, pendencias)
  templates/       # Jinja2 agrupados por dominio
  static/          # css vanilla + js CSP-safe (sem jQuery/framework)
migrations/        # Alembic, 1 migration por mudanca de schema
tests/             # pytest — auth, fluxo, security, moderacao, filters
```

## Padroes OBRIGATORIOS

### Rotas
- Todo controller: `@login_required` + `@{papel}_required` quando aplicavel
- Validar ownership em rotas com `<int:id>`
- Usar `db.session.get(Model, id)` (SQLAlchemy 2.0), nao `Model.query.get(id)`
- POST sempre com CSRF token no template
- Flash categorias: `success`, `error`, `warning`, `info`
- Pattern PRG: POST -> processa -> redirect (nao render direto)

### Models
- Sempre index nas FKs usadas em filtros
- `UniqueConstraint` com nome explicito
- `Numeric(12, 2)` para dinheiro (nunca Float)
- `DateTime` UTC com `default=lambda: datetime.now(timezone.utc)`
- Migrations Alembic com FK name explicito (`fk_...`) — SQLite batch mode exige

### Queries
- `joinedload` para evitar N+1
- Filtros antes de order_by/group_by
- Logica complexa/reutilizada vai pra `services/`
- Controllers finos

### Imports
- **SEMPRE no topo do arquivo** (import local dentro de funcao causa UnboundLocalError)
- Ordem: stdlib -> third-party -> local
- Python 3.12 em `C:/Users/NITRO/AppData/Local/Programs/Python/Python312/python.exe`

### Datetime
- Usar `datetime.utcnow()` ainda aceitavel mas preferir `datetime.now(timezone.utc)`
- NO banco: guardar UTC
- NO display: filtro Jinja `|datetime_br` converte

### Templates
- Escape automatico (nao usar `|safe` sem necessidade critica)
- Reaproveitar classes existentes de `app/static/css/style.css`
- Variaveis CSS: `--primary` (laranja), `--gray-*`, `--white`, `--radius`
- JS externo em `app/static/js/*.js` (CSP nao permite inline)

## Fluxo de implementacao

1. Receber spec do product-manager ou direto do usuario
2. Ler CLAUDE.md + MEMORY.md se existir
3. Pensar em: model change? migration? rotas? templates? testes?
4. Implementar ponta-a-ponta
5. Rodar pytest
6. Smoke test HTTP (usar requests contra localhost:5050)
7. Commit estilo: `feat: descricao curta`, `fix:`, `refactor:`, etc
8. Push

## O que NAO fazer
- Nao mudar a identidade visual sem autorizacao
- Nao quebrar compatibilidade com migrations aplicadas
- Nao introduzir dependencia sem justificar (Flask vanilla, sem frameworks)
- Nao deixar controllers gordos — extrair pra services/
- Nao esquecer testes em fluxo critico novo

## Comandos uteis
```bash
# Rodar Flask
python run.py

# Rodar testes
python -m pytest tests/ -q

# Gerar migration
python -m flask db migrate -m "descricao"
python -m flask db upgrade
```