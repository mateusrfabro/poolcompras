"""Perfil do usuario — edicao de dados + vinculacao Telegram.

Pacote dividido por dominio:
- dados.py: GET/POST /perfil (dados cadastrais, senha, campos sensiveis com reauth)
- telegram.py: fluxo de vinculacao (deep link / manual / OTP / desvincular)
"""
from flask import Blueprint

perfil_bp = Blueprint("perfil", __name__, url_prefix="/perfil")


# Importar submodulos DEPOIS do blueprint pra registrar rotas
from . import dados, telegram  # noqa: E402,F401
