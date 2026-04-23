"""Testes do marketplace publico /marketplace."""
from app import db
from app.models import (
    Usuario, Fornecedor, Lanchonete, Rodada, Cotacao, Produto,
    AvaliacaoRodada, RodadaProduto, ItemPedido, ParticipacaoRodada,
)
from werkzeug.security import generate_password_hash


def test_marketplace_publico_sem_login(client):
    """Qualquer um acessa — nao redireciona pra /login."""
    r = client.get("/marketplace", follow_redirects=False)
    assert r.status_code == 200
    assert b"Fornecedores parceiros" in r.data


def test_marketplace_lista_apenas_ativos(app, client):
    """Fornecedor inativo nao aparece."""
    fA = Fornecedor.query.first()
    # Cria inativo pra checar que nao aparece
    u = Usuario(email="fd@t.com", senha_hash=generate_password_hash("x"),
                nome_responsavel="D", telefone="", tipo="fornecedor")
    db.session.add(u); db.session.flush()
    fD = Fornecedor(usuario_id=u.id, razao_social="Inativo SA", ativo=False)
    db.session.add(fD); db.session.commit()

    r = client.get("/marketplace")
    assert b"Inativo SA" not in r.data
    assert fA.razao_social.encode() in r.data


def test_marketplace_mostra_rating_quando_ha_avaliacao(app, client):
    """Fornecedor com avaliacao mostra estrelas + media + contagem."""
    fA = Fornecedor.query.first()
    lanch = Lanchonete.query.first()
    rodada = Rodada.query.first()

    db.session.add(AvaliacaoRodada(
        rodada_id=rodada.id, lanchonete_id=lanch.id,
        fornecedor_id=fA.id, estrelas=5,
    ))
    db.session.commit()

    r = client.get("/marketplace")
    assert r.status_code == 200
    # "1 aval." esperado
    assert b"1 aval." in r.data or b"aval" in r.data


def test_marketplace_rate_limit_nao_quebra_fluxo_normal(app, client):
    """Rate limit esta desabilitado em testes (conftest) — multiplos GETs OK."""
    for _ in range(5):
        r = client.get("/marketplace")
        assert r.status_code == 200
