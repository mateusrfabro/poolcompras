"""Logica centralizada de pendencias por perfil.

Centraliza as regras de 'o que esta pendente pra cada lanchonete/fornecedor'
pra evitar duplicacao entre dashboard, historico e notificacoes.
"""
from sqlalchemy.orm import joinedload
from app import db
from app.models import ParticipacaoRodada, Rodada, Cotacao


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
    rodadas_cotadas_ids = [
        r for (r,) in db.session.query(Cotacao.rodada_id)
            .filter_by(fornecedor_id=fornecedor_id)
            .distinct().all()
    ]
    if not rodadas_cotadas_ids:
        return []

    participacoes = (
        ParticipacaoRodada.query
        .options(joinedload(ParticipacaoRodada.lanchonete),
                 joinedload(ParticipacaoRodada.rodada))
        .filter(ParticipacaoRodada.rodada_id.in_(rodadas_cotadas_ids))
        .filter(ParticipacaoRodada.aceite_proposta.is_(True))
        .filter(ParticipacaoRodada.comprovante_key.isnot(None))
        .filter(ParticipacaoRodada.entrega_informada_em.is_(None))
        .order_by(ParticipacaoRodada.comprovante_em.asc())
        .all()
    )

    por_rodada = {}
    for p in participacoes:
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