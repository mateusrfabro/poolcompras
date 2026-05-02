"""Logica centralizada de pendencias por perfil.

Centraliza as regras de 'o que esta pendente pra cada lanchonete/fornecedor'
pra evitar duplicacao entre dashboard, historico e notificacoes.
"""
from sqlalchemy import func
from sqlalchemy.orm import joinedload
from app import db
from app.models import ParticipacaoRodada, Rodada, Cotacao, ItemPedido


def pendencias_lanchonete(lanchonete_id):
    """Retorna lista de pendencias da lanchonete (rodadas finalizadas aguardando acao).

    Cada item: {'rodada': Rodada, 'acao': str, 'urgencia': 'alta'|'media'|'baixa'}
    """
    participacoes = (
        ParticipacaoRodada.query
        .filter_by(lanchonete_id=lanchonete_id)
        .join(Rodada, ParticipacaoRodada.rodada_id == Rodada.id)
        .filter(Rodada.status == "finalizada")
        .options(joinedload(ParticipacaoRodada.rodada))
        .all()
    )

    pendencias = []
    for p in participacoes:
        if p.aceite_proposta is None:
            pendencias.append({
                "rodada": p.rodada, "acao": "Aceitar proposta", "urgencia": "alta",
                "participacao": p,
            })
        elif p.aceite_proposta and not p.comprovante_key:
            pendencias.append({
                "rodada": p.rodada, "acao": "Enviar comprovante", "urgencia": "alta",
                "participacao": p,
            })
        elif p.entrega_informada_em and p.recebimento_ok is None:
            pendencias.append({
                "rodada": p.rodada, "acao": "Confirmar recebimento", "urgencia": "media",
                "participacao": p,
            })
        elif p.recebimento_ok and not p.avaliacao_geral:
            pendencias.append({
                "rodada": p.rodada, "acao": "Avaliar a rodada", "urgencia": "baixa",
                "participacao": p,
            })
    return pendencias


def pendencias_fornecedor(fornecedor_id):
    """Retorna pendencias do fornecedor agrupadas por rodada.

    Cada bloco: {'rodada': Rodada, 'aguardando_pagamento': [...], 'aguardando_entrega': [...]}
    """
    # EXISTS subquery substitui 2 queries (distinct rodada_ids + IN (...))
    # por 1 join semantico. Postgres otimiza melhor que array IN com
    # cardinalidade alta — ranking das pendencias do fornecedor.
    cotou_nesta_rodada = (
        db.session.query(Cotacao.id)
        .filter(Cotacao.rodada_id == ParticipacaoRodada.rodada_id)
        .filter(Cotacao.fornecedor_id == fornecedor_id)
        .exists()
    )

    participacoes = (
        ParticipacaoRodada.query
        .options(joinedload(ParticipacaoRodada.lanchonete),
                 joinedload(ParticipacaoRodada.rodada))
        .filter(cotou_nesta_rodada)
        .filter(ParticipacaoRodada.aceite_proposta.is_(True))
        .filter(ParticipacaoRodada.comprovante_key.isnot(None))
        .filter(ParticipacaoRodada.entrega_informada_em.is_(None))
        .order_by(ParticipacaoRodada.comprovante_em.asc())
        .all()
    )
    if not participacoes:
        return []

    # Calcula valor que cada lanchonete deve PAGAR pro fornecedor atual
    # (qtd pedida x preco vencedor da cotacao DELE). 1 query agrupada por
    # (rodada, lanchonete) — evita N+1 no dashboard.
    valor_por_part = {}
    if participacoes:
        rodada_lanch_pares = [(p.rodada_id, p.lanchonete_id) for p in participacoes]
        rodada_ids = list({r for r, _ in rodada_lanch_pares})
        lanch_ids = list({l for _, l in rodada_lanch_pares})
        valores = (
            db.session.query(
                ItemPedido.rodada_id,
                ItemPedido.lanchonete_id,
                func.sum(ItemPedido.quantidade * Cotacao.preco_unitario).label("valor"),
            )
            .join(Cotacao,
                  (Cotacao.rodada_id == ItemPedido.rodada_id)
                  & (Cotacao.produto_id == ItemPedido.produto_id))
            .filter(Cotacao.fornecedor_id == fornecedor_id)
            .filter(Cotacao.selecionada.is_(True))
            .filter(ItemPedido.rodada_id.in_(rodada_ids))
            .filter(ItemPedido.lanchonete_id.in_(lanch_ids))
            .group_by(ItemPedido.rodada_id, ItemPedido.lanchonete_id)
            .all()
        )
        for rid, lid, valor in valores:
            valor_por_part[(rid, lid)] = float(valor or 0)

    por_rodada = {}
    for p in participacoes:
        # Anexa valor da lanchonete pra ESTE fornecedor (regra de privacidade
        # do Ademar: detalhe por lanchonete so apos aceite, pra fornecedor
        # bater conta interna).
        p.valor_para_fornecedor = valor_por_part.get((p.rodada_id, p.lanchonete_id), 0.0)
        rid = p.rodada_id
        if rid not in por_rodada:
            por_rodada[rid] = {
                "rodada": p.rodada,
                "aguardando_pagamento": [],
                "aguardando_entrega": [],
            }
        if not p.pagamento_confirmado_em:
            por_rodada[rid]["aguardando_pagamento"].append(p)
        elif not p.entrega_informada_em:
            por_rodada[rid]["aguardando_entrega"].append(p)
    return list(por_rodada.values())