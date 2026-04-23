"""Testes do marketplace publico /marketplace."""
from app import db
from app.models import (
    Usuario, Fornecedor, Lanchonete, Rodada, AvaliacaoRodada,
)
from werkzeug.security import generate_password_hash


def _optin(forn):
    forn.aparece_no_marketplace = True
    db.session.commit()


def test_marketplace_publico_sem_login(client):
    """Qualquer um acessa — nao redireciona pra /login."""
    r = client.get("/marketplace", follow_redirects=False)
    assert r.status_code == 200
    assert b"Fornecedores parceiros" in r.data


def test_marketplace_nao_lista_sem_optin(app, client):
    """Fornecedor ativo mas SEM aparece_no_marketplace nao aparece (LGPD)."""
    fA = Fornecedor.query.first()
    # fA do seed: ativo=True, aparece_no_marketplace=False (default)
    r = client.get("/marketplace")
    assert fA.razao_social.encode() not in r.data


def test_marketplace_lista_quando_optin(app, client):
    """Fornecedor que autoriza aparece na vitrine."""
    fA = Fornecedor.query.first()
    _optin(fA)
    r = client.get("/marketplace")
    assert fA.razao_social.encode() in r.data


def test_marketplace_ignora_inativo_mesmo_com_optin(app, client):
    """Inativo + optin -> nao aparece (ativo=True eh pre-requisito)."""
    u = Usuario(email="fd@t.com", senha_hash=generate_password_hash("x"),
                nome_responsavel="D", telefone="", tipo="fornecedor")
    db.session.add(u); db.session.flush()
    fD = Fornecedor(usuario_id=u.id, razao_social="Inativo SA",
                    ativo=False, aparece_no_marketplace=True)
    db.session.add(fD); db.session.commit()

    r = client.get("/marketplace")
    assert b"Inativo SA" not in r.data


def test_marketplace_mostra_rating_quando_ha_avaliacao(app, client):
    fA = Fornecedor.query.first()
    _optin(fA)
    lanch = Lanchonete.query.first()
    rodada = Rodada.query.first()

    db.session.add(AvaliacaoRodada(
        rodada_id=rodada.id, lanchonete_id=lanch.id,
        fornecedor_id=fA.id, estrelas=5,
    ))
    db.session.commit()

    r = client.get("/marketplace")
    assert r.status_code == 200
    assert b"aval" in r.data


def test_marketplace_rate_limit_nao_quebra_fluxo_normal(app, client):
    """Rate limit esta desabilitado em testes (conftest) — multiplos GETs OK."""
    for _ in range(5):
        r = client.get("/marketplace")
        assert r.status_code == 200


def test_marketplace_empty_state(app, client):
    """Sem nenhum fornecedor opt-in, mostra empty-state."""
    r = client.get("/marketplace")
    assert r.status_code == 200
    assert b"empty-state" in r.data or b"Ainda n" in r.data
