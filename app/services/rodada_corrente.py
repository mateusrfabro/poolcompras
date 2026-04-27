"""Helper canonico pra obter a "rodada corrente" em cada status do fluxo.

Bug original (R5/2026-04-27): varias rotas usavam
    Rodada.query.filter_by(status="aberta").first()
sem `order_by`, o que retornava a "primeira" rodada aberta pela ordem do
banco — quando o admin movimentava uma rodada (encerrar coleta etc), o
front podia exibir dados de OUTRA rodada aberta paralela. Bug reportado
pelo Ademar em teste com 3 perfis simultaneos.

Solucao: helpers determinsticos que sempre pegam a mais RECENTE no status.
Centralizar evita inconsistencia (uma rota com order_by, outra sem).
"""
from sqlalchemy import select

from app import db
from app.models import Rodada


def rodada_corrente_aberta():
    """Retorna a Rodada mais recente em status='aberta' (ou None).

    Use em rotas que dependem de "qual rodada o pessoal esta interagindo
    agora" — listar pedidos da lanchonete, catalogo, dashboard.
    """
    return db.session.execute(
        select(Rodada)
        .where(Rodada.status == Rodada.STATUS_ABERTA)
        .order_by(Rodada.data_abertura.desc())
    ).scalars().first()


def rodada_corrente_em_negociacao():
    """Retorna a Rodada mais recente em status='em_negociacao' (ou None)."""
    return db.session.execute(
        select(Rodada)
        .where(Rodada.status == Rodada.STATUS_EM_NEGOCIACAO)
        .order_by(Rodada.data_abertura.desc())
    ).scalars().first()
