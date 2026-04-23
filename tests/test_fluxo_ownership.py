"""Testes de ownership nas acoes de fornecedor no fluxo pos-finalizacao.

Regra: fornecedor so marca pagamento/entrega de lanchonete cujos itens ele venceu
(Cotacao.selecionada=True em algum produto pedido pela lanchonete).
"""
from datetime import datetime, timezone

from werkzeug.security import generate_password_hash

from app import db
from app.models import (
    Cotacao, Fornecedor, ItemPedido, Lanchonete, ParticipacaoRodada,
    Produto, Rodada, RodadaProduto, Usuario,
)


def _agora():
    return datetime.now(timezone.utc)


def _cenario_dois_fornecedores():
    """Rodada finalizada. Fornecedor A venceu p/ Lanch A; fornecedor B venceu p/ Lanch B.

    Fornecedor B NAO deve poder confirmar pagamento da Lanch A.
    """
    rodada = Rodada.query.first()
    produto = Produto.query.first()
    lanchA = Lanchonete.query.filter_by(nome_fantasia="Lanch A").first()
    lanchB = Lanchonete.query.filter_by(nome_fantasia="Lanch B").first()
    fA = Fornecedor.query.first()

    # Fornecedor B
    uB = Usuario(email="fornb@test.com",
                 senha_hash=generate_password_hash("testpass"),
                 nome_responsavel="B", telefone="", tipo="fornecedor")
    db.session.add(uB); db.session.flush()
    fB = Fornecedor(usuario_id=uB.id, razao_social="Fornec B")
    db.session.add(fB); db.session.flush()

    # Produto separado pra Lanch B (diferente do p pedido pela Lanch A)
    produtoB = Produto(nome="Patty Halloumi", categoria="Queijo",
                      subcategoria="Fatiado", unidade="kg", ativo=True)
    db.session.add(produtoB); db.session.flush()
    db.session.add(RodadaProduto(rodada_id=rodada.id, produto_id=produtoB.id))

    rp = RodadaProduto.query.filter_by(rodada_id=rodada.id, produto_id=produto.id).first()
    rp.preco_partida = 20.00

    # Cotacoes vencedoras (selecionada=True)
    db.session.add(Cotacao(rodada_id=rodada.id, fornecedor_id=fA.id,
                            produto_id=produto.id, preco_unitario=15.00,
                            selecionada=True))
    db.session.add(Cotacao(rodada_id=rodada.id, fornecedor_id=fB.id,
                            produto_id=produtoB.id, preco_unitario=12.00,
                            selecionada=True))

    # ItemPedido: Lanch A pede produto (de A); Lanch B pede produtoB (de B)
    db.session.add(ItemPedido(rodada_id=rodada.id, lanchonete_id=lanchA.id,
                               produto_id=produto.id, quantidade=10))
    db.session.add(ItemPedido(rodada_id=rodada.id, lanchonete_id=lanchB.id,
                               produto_id=produtoB.id, quantidade=5))

    # Participacoes: Lanch A ja enviou comprovante (pra fornB tentar confirmar)
    db.session.add(ParticipacaoRodada(
        rodada_id=rodada.id, lanchonete_id=lanchA.id,
        pedido_enviado_em=_agora(), pedido_aprovado_em=_agora(),
        aceite_proposta=True, aceite_em=_agora(),
        comprovante_key="dummy.pdf", comprovante_em=_agora(),
    ))
    db.session.add(ParticipacaoRodada(
        rodada_id=rodada.id, lanchonete_id=lanchB.id,
        pedido_enviado_em=_agora(), pedido_aprovado_em=_agora(),
    ))
    rodada.status = "finalizada"
    db.session.commit()
    return rodada.id, lanchA.id, lanchB.id, fA.id, fB.id


def test_fornecedor_b_nao_confirma_pagamento_de_lanchA(app):
    """Fornecedor B nao venceu item da Lanch A — 403 em confirmar-pagamento."""
    rodada_id, lanchA_id, _, _, _ = _cenario_dois_fornecedores()

    c = app.test_client()
    r = c.post("/login", data={"email": "fornb@test.com", "senha": "testpass"},
               follow_redirects=False)
    assert r.status_code == 302

    r = c.post(
        f"/fluxo/rodada/{rodada_id}/lanchonete/{lanchA_id}/pagamento",
        follow_redirects=False,
    )
    assert r.status_code == 403

    # Estado no DB inalterado
    p = ParticipacaoRodada.query.filter_by(
        rodada_id=rodada_id, lanchonete_id=lanchA_id,
    ).first()
    assert p.pagamento_confirmado_em is None


def test_fornecedor_b_nao_informa_entrega_de_lanchA(app):
    """Fornecedor B nao venceu item da Lanch A — 403 em informar-entrega.

    Simula pre-requisito (pagamento confirmado) direto no DB pra evitar
    sobreposicao de sessao entre 2 test clients (quirk do Flask test_client).
    """
    rodada_id, lanchA_id, _, _, _ = _cenario_dois_fornecedores()

    # Pre-requisito: pagamento ja confirmado (pra chegar na rota de entrega)
    p = ParticipacaoRodada.query.filter_by(
        rodada_id=rodada_id, lanchonete_id=lanchA_id,
    ).first()
    p.pagamento_confirmado_em = _agora()
    db.session.commit()

    c = app.test_client()
    r = c.post("/login", data={"email": "fornb@test.com", "senha": "testpass"},
               follow_redirects=False)
    assert r.status_code == 302

    r = c.post(
        f"/fluxo/rodada/{rodada_id}/lanchonete/{lanchA_id}/entrega",
        data={"entrega_data": "2026-04-24"},
        follow_redirects=False,
    )
    assert r.status_code == 403

    p = db.session.get(ParticipacaoRodada, p.id)
    assert p.entrega_informada_em is None


def test_fornecedor_a_confirma_pagamento_da_propria_lanchA(app, client_forn):
    """Caminho feliz: fornecedor A (vencedor da Lanch A) confirma pagamento — ok."""
    rodada_id, lanchA_id, _, _, _ = _cenario_dois_fornecedores()

    r = client_forn.post(
        f"/fluxo/rodada/{rodada_id}/lanchonete/{lanchA_id}/pagamento",
        follow_redirects=False,
    )
    assert r.status_code == 302

    p = ParticipacaoRodada.query.filter_by(
        rodada_id=rodada_id, lanchonete_id=lanchA_id,
    ).first()
    assert p.pagamento_confirmado_em is not None
