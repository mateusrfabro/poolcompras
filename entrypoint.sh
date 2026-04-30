#!/bin/bash
set -e

echo "[poolcompras] Aguardando banco de dados..."
sleep 3

echo "[poolcompras] Aplicando migrations..."
flask db upgrade

# Seed apenas na primeira vez (quando RUN_SEED=true no .env)
if [ "$RUN_SEED" = "true" ]; then
    echo "[poolcompras] Rodando seed inicial..."
    python scripts/seed.py
    python scripts/seed_demo.py
    echo "[poolcompras] Seed concluido. Mude RUN_SEED=false no .env para nao repetir."
else
    echo "[poolcompras] Seed pulado (RUN_SEED != true)."
fi

# Calcula workers: 2*CPU + 1 (ou usa WEB_WORKERS do env)
WORKERS=${WEB_WORKERS:-$(python -c "import os; print(2 * os.cpu_count() + 1)" 2>/dev/null || echo 3)}

echo "[poolcompras] Iniciando gunicorn com $WORKERS workers..."
# --max-requests + jitter: recicla worker apos N requests (libera memoria
# de eventual leak gradual e pega config nova ao reiniciar). Jitter
# evita todos os workers reciclarem ao mesmo tempo.
exec gunicorn \
    --bind 0.0.0.0:${PORT:-5050} \
    --workers "$WORKERS" \
    --timeout 120 \
    --max-requests 1000 \
    --max-requests-jitter 100 \
    --access-logfile /var/log/poolcompras-access.log \
    --error-logfile /var/log/poolcompras-error.log \
    --capture-output \
    run:app