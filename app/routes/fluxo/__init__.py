"""
Acoes de transicao de estado no fluxo de uma rodada.

Cada acao:
1. Valida autorizacao (quem pode executar)
2. Valida pre-requisitos (fase anterior concluida, rodada em status compativel)
3. Atualiza ParticipacaoRodada
4. Gera EventoRodada correspondente (log imutavel)
5. Commit transacional; rollback em erro

Pacote dividido por ator:
- lanchonete.py: aceitar, recusar, comprovante, confirmar_recebimento
- avaliacao.py: avaliar, avaliar_detalhado
- fornecedor.py: confirmar_pagamento, informar_entrega
"""
from datetime import datetime, timezone
from flask import Blueprint, abort
from flask_login import current_user

from app import db
from app.models import (
    Rodada, ParticipacaoRodada, EventoRodada, Cotacao, Fornecedor,
    SubmissaoCotacao, ItemPedido,
)
from app.services.notificacoes import notificar_evento

fluxo_bp = Blueprint("fluxo", __name__, url_prefix="/fluxo")


# Extensoes permitidas para comprovante + whitelist de magic bytes basica
COMPROVANTE_EXT = {"pdf", "jpg", "jpeg", "png"}
MAGIC_BYTES = {
    # PDF sempre comeca com %PDF-
    b"%PDF-": "pdf",
    # JPEG
    b"\xff\xd8\xff": "jpg",
    # PNG
    b"\x89PNG\r\n\x1a\n": "png",
}


def _ja_aceita_fase_aceite(rodada):
    """Rodada aceita aceite quando:
    - status == 'finalizada' (fluxo antigo — admin fechou a rodada), OU
    - status == 'em_negociacao' com ao menos 1 SubmissaoCotacao aprovada
      (fluxo novo — lanchonetes ja podem aceitar proposta parcial)
    """
    if rodada.status == "finalizada":
        return True
    if rodada.status == "em_negociacao":
        return db.session.query(SubmissaoCotacao.id).filter_by(
            rodada_id=rodada.id
        ).filter(SubmissaoCotacao.aprovada_em.isnot(None)).first() is not None
    return False


def _agora():
    return datetime.now(timezone.utc)


def _obter_ou_criar_participacao(rodada_id, lanchonete_id):
    p = ParticipacaoRodada.query.filter_by(
        rodada_id=rodada_id, lanchonete_id=lanchonete_id,
    ).first()
    if not p:
        p = ParticipacaoRodada(rodada_id=rodada_id, lanchonete_id=lanchonete_id)
        db.session.add(p)
        db.session.flush()
    return p


def _registrar_evento(rodada_id, tipo, descricao, lanchonete_id=None, ator_id=None):
    db.session.add(EventoRodada(
        rodada_id=rodada_id,
        lanchonete_id=lanchonete_id,
        ator_id=ator_id,
        tipo=tipo,
        descricao=descricao,
    ))


def _notificar_fornecedores_comprovante(rodada, lanchonete):
    """Notifica fornecedores vencedores que a lanchonete X enviou comprovante."""
    forn_ids = {
        fid for (fid,) in db.session.query(Cotacao.fornecedor_id)
            .join(ItemPedido,
                  (ItemPedido.rodada_id == Cotacao.rodada_id) &
                  (ItemPedido.produto_id == Cotacao.produto_id))
            .filter(Cotacao.rodada_id == rodada.id,
                    Cotacao.selecionada.is_(True),
                    ItemPedido.lanchonete_id == lanchonete.id)
            .distinct().all()
    }
    if not forn_ids:
        return
    for f in Fornecedor.query.filter(Fornecedor.id.in_(forn_ids)).all():
        if f.responsavel:
            notificar_evento(
                f.responsavel,
                "Comprovante recebido",
                f"{lanchonete.nome_fantasia} enviou o comprovante de pagamento "
                f"da rodada '{rodada.nome}'. Confirme o recebimento quando "
                f"conciliar o valor na conta.",
            )


def _so_dona_lanchonete(rodada_id):
    """Garante que current_user e a dona da lanchonete participante. Retorna (rodada, lanchonete)."""
    if not current_user.is_lanchonete or not current_user.lanchonete:
        abort(403)
    rodada = db.get_or_404(Rodada, rodada_id)
    return rodada, current_user.lanchonete


def _so_fornecedor_da_rodada(rodada_id):
    """Garante que current_user e fornecedor que cotou nessa rodada."""
    if not current_user.is_fornecedor or not current_user.fornecedor:
        abort(403)
    rodada = db.get_or_404(Rodada, rodada_id)
    cotou = Cotacao.query.filter_by(
        rodada_id=rodada_id, fornecedor_id=current_user.fornecedor.id,
    ).first()
    if not cotou:
        abort(403)
    return rodada, current_user.fornecedor


def _fornecedor_atende_lanchonete(rodada_id, fornecedor_id, lanchonete_id):
    """True se o fornecedor venceu (selecionada=True) algum produto pedido pela lanchonete.

    Usado pra impedir que fornecedor A marque pagamento/entrega pra lanchonete X
    cujos itens foram todos vencidos por fornecedor B.
    """
    q = (
        db.session.query(Cotacao.id)
        .join(
            ItemPedido,
            (ItemPedido.rodada_id == Cotacao.rodada_id)
            & (ItemPedido.produto_id == Cotacao.produto_id),
        )
        .filter(
            Cotacao.rodada_id == rodada_id,
            Cotacao.fornecedor_id == fornecedor_id,
            Cotacao.selecionada.is_(True),
            ItemPedido.lanchonete_id == lanchonete_id,
        )
    )
    return db.session.query(q.exists()).scalar()


# Importar submodulos DEPOIS do blueprint/helpers pra registrar as rotas
from . import lanchonete, avaliacao, fornecedor  # noqa: E402,F401
