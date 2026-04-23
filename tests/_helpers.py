"""Helpers compartilhados para cenarios recorrentes nos testes.

Meta: DRY em cenarios que apareciam em 6+ arquivos quase identicos.
Cada helper eh uma funcao simples (nao fixture), retorna ids pros testes
manipularem depois. Eh facil de composicao — o teste pode ir MAIS LONGE
que o helper adiciona (ex: mais participacoes, mais produtos).

NAO eh pytest fixture porque os testes atuais sao imperativos e seria
custoso refatorar todos. Objetivo: reutilizar, nao forcar mudanca.
"""
from datetime import datetime, timezone

from app import db
from app.models import (
    Cotacao, Fornecedor, ItemPedido, Lanchonete, ParticipacaoRodada,
    Produto, Rodada, RodadaProduto,
)


def _agora():
    return datetime.now(timezone.utc)


def cenario_rodada_em_negociacao(preco_partida: float = 20.0,
                                  quantidade: float = 10.0,
                                  preco_final_vencedor: float | None = None):
    """Rodada em 'em_negociacao' com 1 pedido aprovado da Lanch A.

    Se preco_final_vencedor for passado, cria Cotacao(selecionada=False)
    do fornecedor primario com esse preco (pronta pra virar vencedora).
    Retorna (rodada_id, lanch_id, forn_id, produto_id).
    """
    rodada = Rodada.query.first()
    produto = Produto.query.first()
    lanch = Lanchonete.query.filter_by(nome_fantasia="Lanch A").first()
    forn = Fornecedor.query.first()

    rp = RodadaProduto.query.filter_by(rodada_id=rodada.id, produto_id=produto.id).first()
    rp.preco_partida = preco_partida

    db.session.add(ItemPedido(
        rodada_id=rodada.id, lanchonete_id=lanch.id,
        produto_id=produto.id, quantidade=quantidade,
    ))
    db.session.add(ParticipacaoRodada(
        rodada_id=rodada.id, lanchonete_id=lanch.id,
        pedido_enviado_em=_agora(),
        pedido_aprovado_em=_agora(),
    ))

    if preco_final_vencedor is not None:
        db.session.add(Cotacao(
            rodada_id=rodada.id, fornecedor_id=forn.id,
            produto_id=produto.id, preco_unitario=preco_final_vencedor,
        ))

    rodada.status = "em_negociacao"
    db.session.commit()
    return rodada.id, lanch.id, forn.id, produto.id


def cenario_rodada_finalizada_com_aceite(preco_partida: float = 20.0,
                                           preco_final: float = 15.0,
                                           quantidade: float = 10.0):
    """Rodada 'finalizada', Cotacao(selecionada=True) do forn primario,
    pedido aprovado da Lanch A e ParticipacaoRodada com aceite_proposta=True.

    Retorna (rodada_id, lanch_id, forn_id, produto_id).
    """
    rodada = Rodada.query.first()
    produto = Produto.query.first()
    lanch = Lanchonete.query.filter_by(nome_fantasia="Lanch A").first()
    forn = Fornecedor.query.first()

    rp = RodadaProduto.query.filter_by(rodada_id=rodada.id, produto_id=produto.id).first()
    rp.preco_partida = preco_partida

    db.session.add(Cotacao(
        rodada_id=rodada.id, fornecedor_id=forn.id,
        produto_id=produto.id, preco_unitario=preco_final, selecionada=True,
    ))
    db.session.add(ItemPedido(
        rodada_id=rodada.id, lanchonete_id=lanch.id,
        produto_id=produto.id, quantidade=quantidade,
    ))
    db.session.add(ParticipacaoRodada(
        rodada_id=rodada.id, lanchonete_id=lanch.id,
        pedido_enviado_em=_agora(),
        pedido_aprovado_em=_agora(),
        aceite_proposta=True,
        aceite_em=_agora(),
    ))
    rodada.status = "finalizada"
    db.session.commit()
    return rodada.id, lanch.id, forn.id, produto.id
