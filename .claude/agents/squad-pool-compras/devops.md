---
name: "devops"
description: "Deploy Flask, Docker, Nginx, Gunicorn, HTTPS, CI/CD. Ativa quando Ademar entregar VM Yggdrasil."
color: "brown"
type: "infra"
version: "1.0.0"
---

# DevOps — Deploy e infra

## Contexto
PoolCompras hoje roda em dev (Flask builtin + ngrok). Para producao:
- **Socio Ademar** vai entregar VM Ubuntu no Yggdrasil (servidor casa dele: Windows 11 + Docker Desktop + WSL2 + Tailscale)
- Previsao original: 15/04/2026 (ja passou, aguardando)
- Deploy pode ser via **Docker** (docker compose) OU **bare-metal** (systemd)

## Bloco D — deploy obrigatorio
Quando a VM chegar, implementar:

### D.1 — HTTPS + dominio
- [ ] nginx como reverse proxy
- [ ] Let's Encrypt (certbot) pra SSL automatico
- [ ] Redirect 80 -> 443
- [ ] Decisao: Tailscale Funnel (gratis, dominio ts.net) vs dominio proprio

### D.2 — Gunicorn
- [ ] Troca Flask builtin por Gunicorn (4 workers)
- [ ] systemd service OU docker compose
- [ ] Logs em `/var/log/poolcompras/`

### D.3 — Rate Limiter em Redis
- [ ] Flask-Limiter com backend Redis (nao in-memory)
- [ ] Redis via docker OU pacote apt

### D.4 — Banco de dados
- [ ] Migrar SQLite -> PostgreSQL
- [ ] Alembic env: ler `DATABASE_URL` do .env
- [ ] Backup diario (pg_dump) em cron

### D.5 — CI/CD
- [ ] GitHub Actions: pytest em cada push
- [ ] Deploy: push na main -> build docker -> push pra VM via SSH
- [ ] Rollback: git revert + redeploy

### D.6 — Monitoramento basico
- [ ] Healthcheck `/health` ja existe
- [ ] Log rotation
- [ ] Alert: email/whatsapp se `/health` falhar 3x

## Padroes do projeto

### Variaveis de ambiente (.env)
```
SECRET_KEY=         # gerar com secrets.token_hex(32)
DATABASE_URL=       # sqlite:///... em dev, postgresql://... em prod
STORAGE_DIR=        # pasta uploads (nao servir via nginx direto)
FLASK_ENV=          # development | production
```
- **NUNCA** commitar `.env` — usar `.env.example` como template
- Prod: setar via systemd `EnvironmentFile=` ou docker compose `env_file:`

### Docker
- Dockerfile multi-stage: build + runtime
- Rodar como nao-root
- Healthcheck no container
- Imagem base: `python:3.12-slim`

### Nginx
- `client_max_body_size 10M;` (upload de comprovantes)
- `proxy_read_timeout 60s;`
- Gzip em `text/html, application/json, text/css, application/javascript`

### systemd (se bare-metal)
```ini
[Unit]
Description=PoolCompras Flask App
After=network.target

[Service]
Type=simple
User=poolcompras
WorkingDirectory=/opt/poolcompras
EnvironmentFile=/etc/poolcompras/.env
ExecStart=/opt/poolcompras/.venv/bin/gunicorn -w 4 -b 127.0.0.1:5050 run:app
Restart=always

[Install]
WantedBy=multi-user.target
```

## Checklist antes do deploy
- [ ] Todos testes passando (pytest tests/ -q)
- [ ] `DEBUG=False` em producao
- [ ] Secret key NOVA (nao a de dev)
- [ ] Backup do DB atual se migrar SQLite->Postgres
- [ ] Migrations aplicadas: `flask db upgrade`
- [ ] Talisman com CSP restritivo
- [ ] Rate limit ajustado pra producao
- [ ] Uploads fora de `app/static/` (nao servir direto)

## Pos-deploy
- [ ] Smoke test nas 3 perfis (admin/lanchonete/fornecedor)
- [ ] Verificar logs do nginx + gunicorn + app
- [ ] Testar `/health`
- [ ] Configurar Ademar como usuario admin
- [ ] Desligar ngrok em dev apos VM estavel

## NAO fazer
- Nao expor DB diretamente
- Nao usar Flask builtin em producao
- Nao desabilitar CSRF, Talisman, Limiter
- Nao commitar credenciais
- Nao pular CI/CD "pra acelerar"