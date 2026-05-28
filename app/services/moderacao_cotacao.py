"""Acoes de moderacao de cotacao final pelo admin.

Extraido de admin/moderacao.py:aprovar_cotacoes pra eliminar o handler
de 115 linhas com 3 branches. API simetrica a moderacao_pedido.

API:
    aprovar(sub, admin, rodada) -> ModeracaoResult
    devolver(sub, admin, rodada) -> ModeracaoResult
    reverter(sub, admin, rodada) -> ModeracaoResult

Aprovar tem side effect adicional: notifica TODAS lanchonetes que tem
proposta nova disponivel pra aceitar.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from app import db
from app.services.notificacoes import (
    notificar_evento, notificar_lanchonetes_cotacao_aprovada,
)
from app.services.moderacao_pedido import ModeracaoResult

logger = logging.getLogger(__name__)


def _agora() -> datetime:
    return datetime.now(timezone.utc)


def _nome_fornecedor(sub) -> str:
    return sub.fornecedor.razao_social if sub.fornecedor else f"#{sub.fornecedor_id}"


def _logar(admin_id: int, acao: str, rodada_id: int, submissao_id: int,
           fornecedor_id: int) -> None:
    logger.info(
        "ADMIN_APROVAR_COTACAO admin=%s acao=%s rodada=%s submissao=%s fornecedor=%s",
        admin_id, acao, rodada_id, submissao_id, fornecedor_id,
    )


def _notificar_fornecedor(sub, titulo: str, detalhes: str) -> None:
    if sub.fornecedor and sub.fornecedor.responsavel:
        notificar_evento(sub.fornecedor.responsavel, titulo, detalhes)


def aprovar(sub, admin, rodada) -> ModeracaoResult:
    """Aprovar cotacao final do fornecedor. Idempotente em cotacao ja aprovada.

    Notifica fornecedor + tambem todas lanchonetes (proposta nova disponivel).
    """
    nome = _nome_fornecedor(sub)
    # 2 admins clicando simultaneo nao devem disparar 2 notifs nem 2 logs.
    if sub.aprovada_em is not None:
        return ModeracaoResult(True, "info", f"Cotacao de {nome} ja estava aprovada.")

    sub.aprovada_em = _agora()
    sub.aprovada_por_id = admin.id
    sub.devolvida_em = None
    db.session.commit()

    _logar(admin.id, "aprovar", rodada.id, sub.id, sub.fornecedor_id)
    _notificar_fornecedor(
        sub,
        "Cotação aprovada",
        f"Sua cotação final na rodada '{rodada.nome}' foi aprovada pelo admin "
        f"e está disponível pras lanchonetes.",
    )
    if sub.fornecedor:
        notificar_lanchonetes_cotacao_aprovada(rodada, sub.fornecedor)

    return ModeracaoResult(False, "success", f"Cotacao de {nome} aprovada.")


def devolver(sub, admin, rodada) -> ModeracaoResult:
    """Devolver cotacao pro fornecedor ajustar. Idempotente quando ja
    devolvida e fornecedor ainda nao reenviou.
    """
    nome = _nome_fornecedor(sub)
    if sub.devolvida_em is not None and sub.enviada_em is None:
        return ModeracaoResult(
            True, "info",
            f"Cotacao de {nome} ja estava devolvida e aguardando reenvio.",
        )

    sub.devolvida_em = _agora()
    sub.enviada_em = None
    sub.aprovada_em = None
    db.session.commit()

    _logar(admin.id, "devolver", rodada.id, sub.id, sub.fornecedor_id)
    _notificar_fornecedor(
        sub,
        "Cotação devolvida",
        f"Sua cotação na rodada '{rodada.nome}' foi devolvida pelo admin. "
        f"Ajuste os preços e reenvie.",
    )
    return ModeracaoResult(
        False, "success", f"Cotação de {nome} devolvida para negociação.",
    )


def reverter(sub, admin, rodada) -> ModeracaoResult:
    """Reverter aprovacao — cotacao volta pra fila. Sem notif."""
    nome = _nome_fornecedor(sub)
    if sub.aprovada_em is None:
        return ModeracaoResult(
            True, "info",
            f"Cotação de {nome} não está aprovada — nada a reverter.",
        )

    sub.aprovada_em = None
    sub.aprovada_por_id = None
    db.session.commit()

    _logar(admin.id, "reverter", rodada.id, sub.id, sub.fornecedor_id)
    return ModeracaoResult(False, "info", f"Aprovacao de {nome} revertida.")
