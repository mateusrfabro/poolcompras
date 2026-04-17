# Deploy PoolCompras

## Opcao 1: Docker (recomendado)

### Pre-requisitos
- Docker + Docker Compose instalados
- Git

### Passo a passo

```bash
# 1. Clonar o repo
git clone https://github.com/mateusrfabro/poolcompras.git
cd poolcompras

# 2. Criar .env a partir do exemplo
cp .env.example .env

# 3. Editar .env com valores reais
#    OBRIGATORIO: SECRET_KEY e DB_PASSWORD
#    Na primeira vez: RUN_SEED=true
nano .env   # ou vim, ou qualquer editor

# 4. Subir tudo
docker compose up -d --build

# 5. Verificar se subiu
docker compose ps
docker compose logs -f app   # ver logs da app

# 6. Acessar
# http://IP_DA_VM:80 (via nginx)
# Login admin: admin@poolcompras.com / admin123

# 7. IMPORTANTE: depois do primeiro deploy, voltar RUN_SEED=false
#    no .env para nao rodar seed de novo no proximo restart.
```

### Comandos uteis

```bash
# Ver logs
docker compose logs -f app
docker compose logs -f nginx

# Parar
docker compose down

# Reiniciar app (sem rebuild)
docker compose restart app

# Rebuild (apos git pull com mudancas no Dockerfile)
docker compose up -d --build

# Aplicar migration manualmente (se entrypoint nao rodar)
docker compose exec app flask db upgrade

# Rodar cron de deadlines manualmente
docker compose exec app flask cron fechar-vencidas
docker compose exec app flask cron status

# Backup do banco
docker compose exec db pg_dump -U poolcompras poolcompras > backup_$(date +%Y%m%d).sql

# Restaurar backup
cat backup_20260417.sql | docker compose exec -T db psql -U poolcompras poolcompras
```

### Crontab (na VM do host)

```bash
crontab -e
# Adicionar:
*/5 * * * * cd /caminho/poolcompras && docker compose exec -T app flask cron fechar-vencidas >> /var/log/poolcompras-cron.log 2>&1
```

---

## Opcao 2: Bare-metal (sem Docker)

### Pre-requisitos
- Python 3.12+
- PostgreSQL 15+ (ou usar SQLite pra teste)
- nginx (opcional, pra HTTPS)

### Passo a passo

```bash
# 1. Clonar
git clone https://github.com/mateusrfabro/poolcompras.git
cd poolcompras

# 2. Criar virtualenv
python -m venv venv
source venv/bin/activate

# 3. Instalar deps
pip install -r requirements.txt

# 4. Criar .env
cp .env.example .env
nano .env
# Setar SECRET_KEY, FLASK_ENV=production
# Se PostgreSQL: DATABASE_URL=postgresql://user:pass@localhost:5432/poolcompras
# Se SQLite (teste): deixar sem DATABASE_URL (usa sqlite:///poolcompras.db)

# 5. Aplicar migrations
export FLASK_APP=run.py
flask db upgrade

# 6. Seed (primeira vez)
python scripts/seed.py
python scripts/seed_demo.py   # opcional: dados de demonstracao

# 7. Rodar com gunicorn
gunicorn --bind 0.0.0.0:5050 --workers 3 --timeout 120 run:app

# 8. Configurar como servico systemd (persistente)
# Ver exemplo abaixo
```

### Exemplo systemd

```ini
# /etc/systemd/system/poolcompras.service
[Unit]
Description=PoolCompras Central de Compras
After=network.target postgresql.service

[Service]
Type=exec
User=poolcompras
WorkingDirectory=/opt/poolcompras
EnvironmentFile=/opt/poolcompras/.env
ExecStart=/opt/poolcompras/venv/bin/gunicorn \
    --bind 127.0.0.1:5050 \
    --workers 3 \
    --timeout 120 \
    --access-logfile /var/log/poolcompras-access.log \
    --error-logfile /var/log/poolcompras-error.log \
    run:app
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable poolcompras
sudo systemctl start poolcompras
sudo systemctl status poolcompras
```

---

## Estrutura de portas

| Servico | Porta | Acesso |
|---------|-------|--------|
| nginx   | 80    | Publico (HTTP) |
| app     | 5050  | Interno (nginx faz proxy) |
| db      | 5433  | Interno (so Docker network) |

## Volumes persistentes (Docker)

| Volume | O que guarda |
|--------|-------------|
| pgdata | Banco PostgreSQL |
| uploads | Comprovantes de pagamento (PDFs/JPGs) |
| logs | Logs do gunicorn |

## Checklist pre-deploy

- [ ] SECRET_KEY gerada (unica, aleatoria, 32+ chars)
- [ ] DB_PASSWORD forte
- [ ] RUN_SEED=true na primeira vez, false depois
- [ ] Firewall: porta 80 aberta, 5050 e 5433 bloqueadas externamente
- [ ] Crontab configurado pra fechar-vencidas
- [ ] Backup automatico do banco (cron + pg_dump)