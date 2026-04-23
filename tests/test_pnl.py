"""Testes da tela Meu P&L do fornecedor + service calcular_pnl.

Paridade com test_cmv.py: espelho do lado oposto da relacao.
"""
from datetime import datetime, timezone
from werkzeug.security import generate_password_hash

from app import db
from app.models import (
    Cotacao, ItemPedido, Lanchonete, Produto, Rodada,
    ParticipacaoRodada, RodadaProduto, Fornecedor, Usuario,
)
from app.services.pnl_fornecedor import calcular_pnl


def _agora():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _prepara_venda_aceita():
    """Cenario: 1 rodada finalizada com cotacao vencida pelo forn primario
    e participacao da lanchA com aceite_proposta=True."""
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
        pedido_enviado_em=_agora(),
        pedido_aprovado_em=_agora(),
        aceite_proposta=True,
        aceite_em=_agora(),
    ))
    rodada.status = "finalizada"
    db.session.commit()
    return rodada.id, lanch.id, forn.id


def test_pnl_zero_quando_sem_vendas(app, client_forn):
    r = client_forn.get("/fornecedor/pnl")
    assert r.status_code == 200
    # Empty state presente
    assert b"n\xc3\xa3o tem rodadas" in r.data or b"Rodadas com venda" in r.data


def test_pnl_calcula_receita_e_margem(app):
    rodada_id, lanch_id, forn_id = _prepara_venda_aceita()
    dados = calcular_pnl(forn_id)
    k = dados["kpis"]
    # 10 kg x R$15 = R$150 receita
    assert k["receita_total"] == 150.00
    # 1 rodada com venda
    assert k["rodadas_vendidas"] == 1
    assert k["ticket_medio"] == 150.00
    # Partida era 20, vendeu a 15: margem negativa de (150 - 200) = -50
    assert k["margem_vs_partida"] == -50.00
    # -50 / 200 * 100 = -25%
    assert k["margem_vs_partida_pct"] == -25.0


def test_pnl_top_clientes_e_produtos(app):
    _, _, forn_id = _prepara_venda_aceita()
    dados = calcular_pnl(forn_id)

    assert len(dados["top_clientes"]) == 1
    nome, gasto, itens, pct = dados["top_clientes"][0]
    assert nome == "Lanch A"
    assert gasto == 150.00
    assert itens == 1
    assert pct == 100.0

    assert len(dados["top_produtos"]) == 1
    pnome, punit, qtd, receita, preco_medio = dados["top_produtos"][0]
    assert pnome == "Blend 180g"
    assert qtd == 10.0
    assert receita == 150.00
    assert preco_medio == 15.0


def test_pnl_por_rodada(app):
    rodada_id, _, forn_id = _prepara_venda_aceita()
    dados = calcular_pnl(forn_id)
    assert len(dados["por_rodada"]) == 1
    r = dados["por_rodada"][0]
    assert r["rodada_id"] == rodada_id
    assert r["receita"] == 150.00
    assert "Lanch A" in r["clientes"]


def test_pnl_ignora_rodada_sem_aceite(app):
    """Cotacao selecionada mas lanchonete nao aceitou = nao entra no P&L."""
    rodada = Rodada.query.first()
    produto = Produto.query.first()
    lanch = Lanchonete.query.filter_by(nome_fantasia="Lanch A").first()
    forn = Fornecedor.query.first()
    rp = RodadaProduto.query.filter_by(rodada_id=rodada.id, produto_id=produto.id).first()
    rp.preco_partida = 10

    db.session.add(Cotacao(rodada_id=rodada.id, fornecedor_id=forn.id,
                            produto_id=produto.id, preco_unitario=8, selecionada=True))
    db.session.add(ItemPedido(rodada_id=rodada.id, lanchonete_id=lanch.id,
                               produto_id=produto.id, quantidade=5))
    db.session.add(ParticipacaoRodada(rodada_id=rodada.id, lanchonete_id=lanch.id,
                                        aceite_proposta=False))
    db.session.commit()

    dados = calcular_pnl(forn.id)
    assert dados["kpis"]["receita_total"] == 0
    assert dados["kpis"]["rodadas_vendidas"] == 0


def test_pnl_isolamento_entre_fornecedores(app):
    """Fornecedor B nao ve vendas de A."""
    _, _, forn_a_id = _prepara_venda_aceita()

    # Cria forn B
    u = Usuario(email="fornb@test.com", senha_hash=generate_password_hash("tp"),
                nome_responsavel="B", telefone="", tipo="fornecedor")
    db.session.add(u)
    db.session.flush()
    fB = Fornecedor(usuario_id=u.id, razao_social="Fornec B")
    db.session.add(fB)
    db.session.commit()

    dados_a = calcular_pnl(forn_a_id)
    dados_b = calcular_pnl(fB.id)

    assert dados_a["kpis"]["receita_total"] == 150.00
    assert dados_b["kpis"]["receita_total"] == 0
    assert dados_b["kpis"]["rodadas_vendidas"] == 0


def test_pnl_lanchonete_nao_acessa(app, client_lanchA):
    r = client_lanchA.get("/fornecedor/pnl", follow_redirects=False)
    assert r.status_code == 302


def test_pnl_admin_nao_acessa(app, client_admin):
    r = client_admin.get("/fornecedor/pnl", follow_redirects=False)
    assert r.status_code == 302


def test_pnl_paridade_com_cmv(app):
    """Receita do fornecedor == Gasto da lanchonete (mesma compra, lados opostos).

    Garante que as duas queries (cmv_lanchonete.py e pnl_fornecedor.py)
    batem matematicamente.
    """
    rodada_id, lanch_id, forn_id = _prepara_venda_aceita()
    from app.services.cmv_lanchonete import calcular_cmv

    cmv = calcular_cmv(lanch_id)
    pnl = calcular_pnl(forn_id)

    assert cmv["kpis"]["gasto_total"] == pnl["kpis"]["receita_total"]
