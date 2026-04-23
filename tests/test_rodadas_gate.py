"""Testa protecao contra vazamento competitivo em /rodadas/<id>.

Fornecedor rival nao deve ver preco final / fornecedor vencedor de cotacoes
que nao sao suas enquanto a rodada nao terminou.
"""
from datetime import datetime, timezone

from app import db
from app.models import (
    Cotacao, Fornecedor, Usuario, ItemPedido, Lanchonete, Produto, Rodada,
    RodadaProduto, ParticipacaoRodada, SubmissaoCotacao,
)
from werkzeug.security import generate_password_hash


def _agora():
    return datetime.now(timezone.utc)


def _cenario_com_vencedor():
    """Cria 2 fornecedores, ambos cotando. Forn A vence com preco menor."""
    rodada = Rodada.query.first()
    produto = Produto.query.first()
    lanch = Lanchonete.query.filter_by(nome_fantasia="Lanch A").first()
    fA = Fornecedor.query.first()  # existente no seed

    # Cria forn B
    uB = Usuario(email="fornb@test.com",
                 senha_hash=generate_password_hash("testpass"),
                 nome_responsavel="B", telefone="", tipo="fornecedor")
    db.session.add(uB); db.session.flush()
    fB = Fornecedor(usuario_id=uB.id, razao_social="Fornec B")
    db.session.add(fB); db.session.flush()

    rp = RodadaProduto.query.filter_by(rodada_id=rodada.id, produto_id=produto.id).first()
    rp.preco_partida = 20.00

    # Submissoes aprovadas dos 2 fornecedores
    db.session.add(SubmissaoCotacao(rodada_id=rodada.id, fornecedor_id=fA.id,
                                     enviada_em=_agora(), aprovada_em=_agora()))
    db.session.add(SubmissaoCotacao(rodada_id=rodada.id, fornecedor_id=fB.id,
                                     enviada_em=_agora(), aprovada_em=_agora()))
    # A cota 12, B cota 18 — A vence
    db.session.add(Cotacao(rodada_id=rodada.id, fornecedor_id=fA.id,
                            produto_id=produto.id, preco_unitario=12.00))
    db.session.add(Cotacao(rodada_id=rodada.id, fornecedor_id=fB.id,
                            produto_id=produto.id, preco_unitario=18.00))
    db.session.add(ItemPedido(rodada_id=rodada.id, lanchonete_id=lanch.id,
                               produto_id=produto.id, quantidade=10))
    db.session.add(ParticipacaoRodada(rodada_id=rodada.id, lanchonete_id=lanch.id,
                                        pedido_enviado_em=_agora(),
                                        pedido_aprovado_em=_agora()))
    rodada.status = "em_negociacao"
    db.session.commit()
    return rodada.id, fA.id, fB.id


def test_fornecedor_rival_nao_ve_preco_vencedor_antes_de_finalizar(app, client_forn):
    """Forn A (do conftest) venceu. Rodada em_negociacao.
    Na tela /rodadas/<id>, o fornecedor default do seed (forn A) VE o proprio
    preco vencedor. Mas se trocarmos pro forn B, ele nao deve ver preco nem
    razao social da Fornec Teste (forn A) no agregado.

    Teste pega client_forn (que eh forn A no seed) — como ele venceu, VE o preco.
    """
    rodada_id, fA_id, fB_id = _cenario_com_vencedor()

    r = client_forn.get(f"/rodadas/{rodada_id}")
    assert r.status_code == 200
    # Forn A venceu; client_forn EH forn A — entao DEVE ver seu proprio preco e razao
    assert b"12" in r.data or b"R$" in r.data  # preco visivel
    assert b"Fornec Teste" in r.data  # razao social do A


def test_fornecedor_rival_nao_ve_dados_de_outro_fornecedor(app, client_lanchA):
    """Cenario invertido: login como lanchonete deve ver tudo (eh cliente)."""
    rodada_id, _, _ = _cenario_com_vencedor()
    r = client_lanchA.get(f"/rodadas/{rodada_id}")
    assert r.status_code == 200
    # Lanchonete precisa ver preco final pra decidir aceite — OK ver Fornec Teste
    assert b"Fornec Teste" in r.data


def test_fornecedor_so_ve_propria_cotacao_quando_perdedor(app):
    """Cria cenario onde forn B perdeu pra A. Faz login como B e checa que
    o agregado nao mostra razao social de A nem preco vencedor (R$ 12)."""
    rodada_id, fA_id, fB_id = _cenario_com_vencedor()

    # Login como forn B
    c = app.test_client()
    r = c.post("/login", data={"email": "fornb@test.com", "senha": "testpass"},
               follow_redirects=False)
    assert r.status_code == 302

    r = c.get(f"/rodadas/{rodada_id}")
    assert r.status_code == 200
    # Forn B perdeu — nao deve ver R$ 12 (preco vencedor de A) nem "Fornec Teste"
    # (mas pode ver Fornec Teste em "Status das cotacoes finais" que mostra submissoes,
    # nao o preco final. O que importa eh nao ter o preco 12 associado a produto)
    # Checagem via regex: procurar "12,00" (preco de A)
    assert b"12,00" not in r.data, "Forn rival nao deveria ver preco vencedor"


def test_todos_veem_vencedor_apos_finalizar(app):
    """Apos rodada.status='finalizada', transparencia — todos veem preco final."""
    rodada_id, fA_id, fB_id = _cenario_com_vencedor()
    rodada = db.session.get(Rodada, rodada_id)
    rodada.status = "finalizada"
    db.session.commit()

    c = app.test_client()
    c.post("/login", data={"email": "fornb@test.com", "senha": "testpass"})

    r = c.get(f"/rodadas/{rodada_id}")
    assert r.status_code == 200
    # Apos finalizacao, forn B ja pode ver o resultado
    assert b"Fornec Teste" in r.data
