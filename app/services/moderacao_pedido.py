"""Acoes de moderacao de pedido pelo admin.

Extraido de admin/moderacao.py:moderar_pedidos pra eliminar o handler
de 115 linhas com 4 branches. Cada acao eh idempotente (guard de
estado terminal) e ja faz commit + log + notif sincronos.

API:
    aprovar(part, admin, rodada) -> ModeracaoResult
    devolver(part, admin, rodada, motivo) -> ModeracaoResult
    reprovar(part, admin, rodada) -> ModeracaoResult
    reverter(part, admin, rodada) -> ModeracaoResult

Idempotencia: se a acao ja foi aplicada (ex: aprovar pedido ja aprovado),
retorna result.idempotente=True com flash informativo, sem mutar/logar/notificar.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from app import db
from app.services.notificacoes import notificar_evento

logger = logging.getLogger(__name__)


@dataclass
class ModeracaoResult:
    """Resultado de uma operacao de moderacao.

    idempotente=True indica que a acao ja estava aplicada — caller geralmente
    so precisa fazer flash + redirect sem outras side effects.
    """
    idempotente: bool
    flash_tipo: str  # success / info / warning / error
    flash_msg: str


def _agora() -> datetime:
    return datetime.now(timezone.utc)


def _nome_lanchonete(part) -> str:
    return part.lanchonete.nome_fantasia if part.lanchonete else f"#{part.lanchonete_id}"


def _logar(admin_id: int, acao: str, rodada_id: int, lanchonete_id: int) -> None:
    logger.info(
        "ADMIN_MODERAR_PEDIDO admin=%s acao=%s rodada=%s lanchonete=%s",
        admin_id, acao, rodada_id, lanchonete_id,
    )


def _notificar(part, titulo: str, detalhes: str) -> None:
    """Notif eh best-effort — nao bloqueia se nao houver canal."""
    if part.lanchonete and part.lanchonete.responsavel:
        notificar_evento(part.lanchonete.responsavel, titulo, detalhes)


def aprovar(part, admin, rodada) -> ModeracaoResult:
    """Aprovar pedido da lanchonete. Idempotente em pedido ja aprovado."""
    nome = _nome_lanchonete(part)
    # 2 cliques rapidos / 2 admins simultaneos nao geram 2 notifs.
    if part.pedido_aprovado_em is not None:
        return ModeracaoResult(True, "info", f"Pedido de {nome} ja estava aprovado.")

    part.pedido_aprovado_em = _agora()
    part.pedido_aprovado_por_id = admin.id
    part.pedido_devolvido_em = None
    part.pedido_reprovado_em = None
    db.session.commit()

    _logar(admin.id, "aprovar", rodada.id, part.lanchonete_id)
    _notificar(
        part,
        "Pedido aprovado",
        f"Seu pedido na rodada '{rodada.nome}' foi aprovado e entrou no pool.",
    )
    return ModeracaoResult(False, "success", f"Pedido de {nome} aprovado.")


def devolver(part, admin, rodada, motivo: str | None) -> ModeracaoResult:
    """Devolver pedido pra lanchonete ajustar. Idempotente quando ja devolvido
    e lanchonete ainda nao reenviou (pedido_enviado_em is None).
    """
    nome = _nome_lanchonete(part)
    if part.pedido_devolvido_em is not None and part.pedido_enviado_em is None:
        return ModeracaoResult(
            True, "info",
            f"Pedido de {nome} ja estava devolvido e aguardando reenvio.",
        )

    part.pedido_devolvido_em = _agora()
    part.pedido_motivo_devolucao = motivo
    part.pedido_enviado_em = None
    part.pedido_aprovado_em = None
    db.session.commit()

    _logar(admin.id, "devolver", rodada.id, part.lanchonete_id)
    motivo_txt = f" Motivo: {motivo}." if motivo else ""
    _notificar(
        part,
        "Pedido devolvido",
        f"Seu pedido na rodada '{rodada.nome}' foi devolvido pelo admin.{motivo_txt} "
        f"Ajuste e reenvie.",
    )
    return ModeracaoResult(False, "success", f"Pedido de {nome} devolvido a lanchonete.")


def reprovar(part, admin, rodada) -> ModeracaoResult:
    """Reprovar definitivamente o pedido. Estado terminal — idempotente
    quando ja reprovado.
    """
    nome = _nome_lanchonete(part)
    if part.pedido_reprovado_em is not None:
        return ModeracaoResult(True, "info", f"Pedido de {nome} ja estava reprovado.")

    part.pedido_reprovado_em = _agora()
    part.pedido_aprovado_em = None
    db.session.commit()

    _logar(admin.id, "reprovar", rodada.id, part.lanchonete_id)
    _notificar(
        part,
        "Pedido reprovado",
        f"Seu pedido na rodada '{rodada.nome}' foi reprovado pelo admin. "
        f"Contate-nos se precisar.",
    )
    return ModeracaoResult(False, "warning", f"Pedido de {nome} reprovado.")


def reverter(part, admin, rodada) -> ModeracaoResult:
    """Reverter aprovacao — pedido volta pra fila de moderacao. Sem notif
    (admin desfazendo proprio ato; lanchonete nao precisa saber).
    """
    nome = _nome_lanchonete(part)
    if part.pedido_aprovado_em is None:
        return ModeracaoResult(
            True, "info",
            f"Pedido de {nome} não está aprovado — nada a reverter.",
        )

    part.pedido_aprovado_em = None
    part.pedido_aprovado_por_id = None
    db.session.commit()

    _logar(admin.id, "reverter", rodada.id, part.lanchonete_id)
    return ModeracaoResult(
        False, "info",
        f"Aprovacao de {nome} revertida. Pedido voltou a aguardar moderacao.",
    )
