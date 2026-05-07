"""Servicos do Kanban de rodadas (visao admin operacional).

Agrega rodadas por status pro Kanban global e gera "situacao" detalhada
por rodada — quem ja lancou pedido, quem aprovou, quem pagou, quem
entregou, quem confirmou.
"""
from __future__ import annotations

from collections import OrderedDict
from datetime import datetime, timezone

from sqlalchemy import select, func
from sqlalchemy.orm import joinedload

from app import db
from app.models import (
    Rodada, ParticipacaoRodada, Lanchonete, Cotacao, Fornecedor,
)


# Ordem das colunas (alinhada com STATUS_VALIDOS de Rodada).
STATUS_KANBAN_RODADAS = (
    Rodada.STATUS_PREPARANDO,
    Rodada.STATUS_AGUARDANDO_COTACAO,
    Rodada.STATUS_ABERTA,
    Rodada.STATUS_EM_NEGOCIACAO,
    Rodada.STATUS_FINALIZADA,
    Rodada.STATUS_CANCELADA,
)

STATUS_LABELS = {
    Rodada.STATUS_PREPARANDO:         "Preparando",
    Rodada.STATUS_AGUARDANDO_COTACAO: "Aguardando cotação",
    Rodada.STATUS_ABERTA:             "Aberta (lanchonetes pedindo)",
    Rodada.STATUS_EM_NEGOCIACAO:      "Em negociação",
    Rodada.STATUS_FINALIZADA:         "Finalizada",
    Rodada.STATUS_CANCELADA:          "Cancelada",
}


def rodadas_por_status() -> dict[str, list[dict]]:
    """Agrupa rodadas por status com contagens pro card.

    Returns:
        OrderedDict {status: [{rodada, qtd_participantes, qtd_aprovados,
                                qtd_aceites, qtd_pagamentos, qtd_entregas}, ...]}
    """
    rodadas = db.session.scalars(
        select(Rodada).order_by(Rodada.data_fechamento.desc())
    ).all()

    grupos: dict[str, list[dict]] = OrderedDict(
        (s, []) for s in STATUS_KANBAN_RODADAS
    )

    for r in rodadas:
        # Subquery agregadas — uma por rodada eh OK no MVP. Em escala,
        # vira 1 query agregada com GROUP BY status. Hoje rodadas sao
        # ~1/dia, custo desprezivel.
        participantes = db.session.scalar(
            select(func.count(ParticipacaoRodada.id))
            .where(ParticipacaoRodada.rodada_id == r.id)
        ) or 0
        aprovados = db.session.scalar(
            select(func.count(ParticipacaoRodada.id))
            .where(ParticipacaoRodada.rodada_id == r.id)
            .where(ParticipacaoRodada.pedido_aprovado_em.isnot(None))
        ) or 0
        aceites = db.session.scalar(
            select(func.count(ParticipacaoRodada.id))
            .where(ParticipacaoRodada.rodada_id == r.id)
            .where(ParticipacaoRodada.aceite_proposta.is_(True))
        ) or 0
        pagamentos = db.session.scalar(
            select(func.count(ParticipacaoRodada.id))
            .where(ParticipacaoRodada.rodada_id == r.id)
            .where(ParticipacaoRodada.pagamento_confirmado_em.isnot(None))
        ) or 0
        entregas = db.session.scalar(
            select(func.count(ParticipacaoRodada.id))
            .where(ParticipacaoRodada.rodada_id == r.id)
            .where(ParticipacaoRodada.entrega_informada_em.isnot(None))
        ) or 0

        grupo = grupos.setdefault(r.status, [])
        grupo.append({
            "rodada": r,
            "qtd_participantes": participantes,
            "qtd_aprovados": aprovados,
            "qtd_aceites": aceites,
            "qtd_pagamentos": pagamentos,
            "qtd_entregas": entregas,
        })
    return grupos


def situacao_rodada(rodada_id: int) -> dict:
    """Drill-down: status individual de cada participante na rodada.

    Pra cada lanchonete: rascunho/enviado/aprovado/devolvido/reprovado,
    aceite, pagamento, entrega, recebimento. Pra cada fornecedor: cotou,
    aprovado pela aggron, etc.

    Returns:
        {
            "rodada": Rodada,
            "lanchonetes": [{participacao, lanchonete, etapa}, ...],
            "fornecedores": [{fornecedor, qtd_cotacoes, qtd_selecionadas}, ...],
        }
    """
    rodada = db.session.get(Rodada, rodada_id)
    if rodada is None:
        return {}

    participacoes = db.session.scalars(
        select(ParticipacaoRodada)
        .options(joinedload(ParticipacaoRodada.lanchonete))
        .where(ParticipacaoRodada.rodada_id == rodada_id)
        .order_by(ParticipacaoRodada.criado_em.asc())
    ).all()

    lanchonetes_info = []
    for p in participacoes:
        lanchonetes_info.append({
            "participacao": p,
            "lanchonete": p.lanchonete,
            "etapa": _etapa_da_participacao(p),
        })

    # Fornecedores que cotaram nesta rodada
    fornecedores_q = (
        select(
            Fornecedor.id, Fornecedor.razao_social,
            func.count(Cotacao.id).label("qtd_cotacoes"),
            func.sum(
                db.case((Cotacao.selecionada.is_(True), 1), else_=0)
            ).label("qtd_selecionadas"),
        )
        .join(Cotacao, Cotacao.fornecedor_id == Fornecedor.id)
        .where(Cotacao.rodada_id == rodada_id)
        .group_by(Fornecedor.id, Fornecedor.razao_social)
        .order_by(Fornecedor.razao_social)
    )
    fornecedores_info = []
    for row in db.session.execute(fornecedores_q).all():
        fornecedores_info.append({
            "fornecedor_id": row.id,
            "razao_social": row.razao_social,
            "qtd_cotacoes": row.qtd_cotacoes or 0,
            "qtd_selecionadas": row.qtd_selecionadas or 0,
        })

    return {
        "rodada": rodada,
        "lanchonetes": lanchonetes_info,
        "fornecedores": fornecedores_info,
    }


def _etapa_da_participacao(p) -> str:
    """Rotulo legivel da etapa atual da lanchonete na rodada.

    Ordem (mais avancada vence): avaliou > recebeu > entrega informada >
    pagamento confirmado > comprovante > aceitou > pedido aprovado >
    pedido enviado > rascunho.
    """
    if p.avaliacao_em:
        return "avaliou"
    if p.recebimento_em:
        return "recebido"
    if p.entrega_informada_em:
        return "entrega informada"
    if p.pagamento_confirmado_em:
        return "pagamento confirmado"
    if p.comprovante_em:
        return "comprovante enviado"
    if p.aceite_proposta is True:
        return "aceitou proposta"
    if p.aceite_proposta is False:
        return "recusou proposta"
    if p.pedido_reprovado_em:
        return "pedido reprovado"
    if p.pedido_devolvido_em:
        return "pedido devolvido"
    if p.pedido_aprovado_em:
        return "pedido aprovado"
    if p.pedido_enviado_em:
        return "pedido enviado (aguardando moderação)"
    return "rascunho"
