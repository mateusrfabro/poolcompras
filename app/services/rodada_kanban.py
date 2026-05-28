"""Servicos do Kanban de rodadas (visao admin operacional).

Agrega rodadas por status pro Kanban global e gera "situacao" detalhada
por rodada — quem ja lancou pedido, quem aprovou, quem pagou, quem
entregou, quem confirmou.
"""
from __future__ import annotations

from collections import OrderedDict

from sqlalchemy import select, func
from sqlalchemy.orm import joinedload

from app import db
from app.models import (
    Rodada, ParticipacaoRodada, Cotacao, Fornecedor,
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

    1 query agregada com SUM(CASE WHEN ...) por bucket — antes eram 5
    SELECT COUNT por rodada (5N queries). Com 30 rodadas: 150 → 1.

    Returns:
        OrderedDict {status: [{rodada, qtd_participantes, qtd_aprovados,
                                qtd_aceites, qtd_pagamentos, qtd_entregas}, ...]}
    """
    grupos: dict[str, list[dict]] = OrderedDict(
        (s, []) for s in STATUS_KANBAN_RODADAS
    )

    # SUM(CASE WHEN ...) eh portavel SQLite + Postgres (FILTER do PG seria
    # mais legivel, mas nao funciona em SQLite). count() nullable retorna 0
    # via outerjoin pra rodadas sem participantes.
    def _count_if(condition):
        return func.coalesce(
            func.sum(db.case((condition, 1), else_=0)), 0
        )

    q = (
        select(
            Rodada.id, Rodada.nome, Rodada.status, Rodada.data_fechamento,
            func.count(ParticipacaoRodada.id).label("qtd_participantes"),
            _count_if(ParticipacaoRodada.pedido_aprovado_em.isnot(None))
                .label("qtd_aprovados"),
            _count_if(ParticipacaoRodada.aceite_proposta.is_(True))
                .label("qtd_aceites"),
            _count_if(ParticipacaoRodada.pagamento_confirmado_em.isnot(None))
                .label("qtd_pagamentos"),
            _count_if(ParticipacaoRodada.entrega_informada_em.isnot(None))
                .label("qtd_entregas"),
        )
        .outerjoin(ParticipacaoRodada,
                   ParticipacaoRodada.rodada_id == Rodada.id)
        .group_by(Rodada.id, Rodada.nome, Rodada.status, Rodada.data_fechamento)
        .order_by(Rodada.data_fechamento.desc())
    )

    # Mapeia row -> dict + carrega Rodada por id (cheap: rodadas ja
    # estao no identity map se chamados anteriormente).
    for row in db.session.execute(q).all():
        rodada = db.session.get(Rodada, row.id)
        grupos.setdefault(row.status, []).append({
            "rodada": rodada,
            "qtd_participantes": row.qtd_participantes or 0,
            "qtd_aprovados": row.qtd_aprovados or 0,
            "qtd_aceites": row.qtd_aceites or 0,
            "qtd_pagamentos": row.qtd_pagamentos or 0,
            "qtd_entregas": row.qtd_entregas or 0,
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
