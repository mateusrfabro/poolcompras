"""Testes da tela Meu CMV da lanchonete + service de calculo."""
from datetime import datetime, timezone
from app import db
from app.models import (
    Cotacao, ItemPedido, Lanchonete, Produto, Rodada,
    ParticipacaoRodada, RodadaProduto, Fornecedor,
)
from app.services.cmv_lanchonete import calcular_cmv


def _prepara_compra_aceita():
    """Cria cenario: rodada com RodadaProduto preco_partida, Cotacao vencedora,
    ItemPedido aprovado e Participacao com aceite_proposta=True."""
    rodada = Rodada.query.first()
    produto = Produto.query.first()
    lanch = Lanchonete.query.filter_by(nome_fantasia="Lanch A").first()
    forn = Fornecedor.query.first()

    rp = RodadaProduto.query.filter_by(rodada_id=rodada.id, produto_id=produto.id).first()
    rp.preco_partida = 20.00

    db.session.add(Cotacao(
        rodada_id=rodada.id, fornecedor_id=forn.id,
        produto_id=produto.id, preco_unitario=15.00, selecionada=True,
    ))
    db.session.add(ItemPedido(
        rodada_id=rodada.id, lanchonete_id=lanch.id,
        produto_id=produto.id, quantidade=10,
    ))
    db.session.add(ParticipacaoRodada(
        rodada_id=rodada.id, lanchonete_id=lanch.id,
        pedido_enviado_em=datetime.now(timezone.utc).replace(tzinfo=None),
        pedido_aprovado_em=datetime.now(timezone.utc).replace(tzinfo=None),
        aceite_proposta=True,
        aceite_em=datetime.now(timezone.utc).replace(tzinfo=None),
    ))
    rodada.status = "finalizada"
    db.session.commit()
    return rodada.id, lanch.id


def test_cmv_zero_quando_nao_comprou(app, client_lanchA):
    r = client_lanchA.get("/minhas-rodadas/cmv")
    assert r.status_code == 200
    # Body contem a secao de empty state
    assert b"n\xc3\xa3o aceitou nenhuma proposta" in r.data.lower() or \
           b"rodadas compradas" in r.data.lower()


def test_cmv_calcula_gasto_e_economia(app):
    rodada_id, lanch_id = _prepara_compra_aceita()
    dados = calcular_cmv(lanch_id)
    k = dados["kpis"]
    # 10 kg x R$15 = R$150 gasto
    assert k["gasto_total"] == 150.00
    # economia: (20-15) x 10 = R$50
    assert k["economia_total"] == 50.00
    assert k["rodadas_compradas"] == 1
    assert k["ticket_medio"] == 150.00

    # Top categoria: Carne = 150, 100%
    assert len(dados["top_categorias"]) == 1
    nome, gasto, pct = dados["top_categorias"][0]
    assert nome == "Carne"
    assert gasto == 150.00
    assert pct == 100.0

    # Top produto
    assert len(dados["top_produtos"]) == 1
    pnome, punit, qtd, gasto, preco_medio = dados["top_produtos"][0]
    assert pnome == "Blend 180g"
    assert qtd == 10.0
    assert gasto == 150.00
    assert preco_medio == 15.0

    # Por rodada
    assert len(dados["por_rodada"]) == 1
    r = dados["por_rodada"][0]
    assert r["gasto"] == 150.00
    assert r["economia"] == 50.00
    assert "Fornec Teste" in r["fornecedores"]


def test_cmv_ignora_rodadas_nao_aceitas(app):
    """Se a lanchonete nao aceitou a proposta (aceite_proposta != True),
    rodada nao entra no CMV."""
    rodada = Rodada.query.first()
    produto = Produto.query.first()
    lanch = Lanchonete.query.filter_by(nome_fantasia="Lanch A").first()
    forn = Fornecedor.query.first()

    rp = RodadaProduto.query.filter_by(rodada_id=rodada.id, produto_id=produto.id).first()
    rp.preco_partida = 10.00

    db.session.add(Cotacao(
        rodada_id=rodada.id, fornecedor_id=forn.id,
        produto_id=produto.id, preco_unitario=8.00, selecionada=True,
    ))
    db.session.add(ItemPedido(
        rodada_id=rodada.id, lanchonete_id=lanch.id,
        produto_id=produto.id, quantidade=5,
    ))
    # Participacao com aceite_proposta=False (recusou)
    db.session.add(ParticipacaoRodada(
        rodada_id=rodada.id, lanchonete_id=lanch.id,
        pedido_aprovado_em=datetime.now(timezone.utc).replace(tzinfo=None),
        aceite_proposta=False,
    ))
    db.session.commit()

    dados = calcular_cmv(lanch.id)
    assert dados["kpis"]["gasto_total"] == 0
    assert dados["kpis"]["rodadas_compradas"] == 0


def test_cmv_isolamento_entre_lanchonetes(app):
    """Lanchonete A compra, lanchonete B nao ve o gasto de A."""
    rodada_id, lanchA_id = _prepara_compra_aceita()
    lanchB = Lanchonete.query.filter_by(nome_fantasia="Lanch B").first()

    dados_a = calcular_cmv(lanchA_id)
    dados_b = calcular_cmv(lanchB.id)

    assert dados_a["kpis"]["gasto_total"] == 150.00
    assert dados_b["kpis"]["gasto_total"] == 0
    assert dados_b["kpis"]["rodadas_compradas"] == 0


def test_cmv_fornecedor_nao_acessa_tela(app, client_forn):
    r = client_forn.get("/minhas-rodadas/cmv", follow_redirects=False)
    assert r.status_code == 302


def test_cmv_admin_nao_acessa_tela(app, client_admin):
    r = client_admin.get("/minhas-rodadas/cmv", follow_redirects=False)
    assert r.status_code == 302
