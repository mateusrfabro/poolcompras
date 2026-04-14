#!/bin/bash
set -e

echo "Aguardando banco de dados..."
sleep 3

echo "Rodando seed (se necessario)..."
python scripts/seed.py

echo "Iniciando aplicacao..."
exec gunicorn --bind 0.0.0.0:5050 --workers 4 --timeout 120 run:app