FROM python:3.12-slim

WORKDIR /app

# Dependencias do sistema
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

# Dependencias Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Codigo da aplicacao
COPY . .
RUN chmod +x entrypoint.sh

# Variavel de ambiente
ENV FLASK_ENV=production

# Porta
EXPOSE 5050

# Entrypoint com seed + gunicorn
CMD ["./entrypoint.sh"]
