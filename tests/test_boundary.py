"""Boundary tests: valores fora do range esperado em campos numericos.

Reforca os CheckConstraints adicionados na migration d8e9fa130601:
- preco_unitario > 0
- quantidade > 0
- estrelas BETWEEN 1 AND 5
- avaliacao_geral entre 1 e 5

Garante que: (a) DB rejeita INSERT direto fora do range; (b) rotas
HTTP rejeitam input fora do range com flash, sem 500.
"""
import re
import pytest
from sqlalchemy.exc import IntegrityError

from app import db
from app.models import (
    AvaliacaoRodada, Cotacao, Fornecedor, ItemPedido, Lanchonete,
    ParticipacaoRodada, Produto, Rodada,
)
from ._helpers import cenario_rodada_finalizada_com_aceite


def _csrf(client, url):
    r = client.get(url)
    m = re.search(rb'name="csrf_token"[^>]*value="([^"]+)"', r.data)
    return m.group(1).decode() if m else None


# ---------- DB-level (CheckConstraints) ----------

def test_db_rejeita_cotacao_preco_zero(app):
    rodada = Rodada.query.first()
    forn = Fornecedor.query.first()
    produto = Produto.query.first()
    db.session.add(Cotacao(
        rodada_id=rodada.id, fornecedor_id=forn.id,
        produto_id=produto.id, preco_unitario=0,
    ))
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_db_rejeita_cotacao_preco_negativo(app):
    rodada = Rodada.query.first()
    forn = Fornecedor.query.first()
    produto = Produto.query.first()
    db.session.add(Cotacao(
        rodada_id=rodada.id, fornecedor_id=forn.id,
        produto_id=produto.id, preco_unitario=-5,
    ))
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_db_rejeita_item_qtd_zero(app):
    rodada = Rodada.query.first()
    lanch = Lanchonete.query.first()
    produto = Produto.query.first()
    db.session.add(ItemPedido(
        rodada_id=rodada.id, lanchonete_id=lanch.id,
        produto_id=produto.id, quantidade=0,
    ))
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_db_rejeita_avaliacao_estrelas_zero(app):
    rodada = Rodada.query.first()
    lanch = Lanchonete.query.first()
    forn = Fornecedor.query.first()
    db.session.add(AvaliacaoRodada(
        rodada_id=rodada.id, lanchonete_id=lanch.id,
        fornecedor_id=forn.id, estrelas=0,
    ))
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_db_rejeita_avaliacao_estrelas_seis(app):
    rodada = Rodada.query.first()
    lanch = Lanchonete.query.first()
    forn = Fornecedor.query.first()
    db.session.add(AvaliacaoRodada(
        rodada_id=rodada.id, lanchonete_id=lanch.id,
        fornecedor_id=forn.id, estrelas=6,
    ))
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_db_rejeita_participacao_avaliacao_seis(app):
    rodada = Rodada.query.first()
    lanch = Lanchonete.query.first()
    db.session.add(ParticipacaoRodada(
        rodada_id=rodada.id, lanchonete_id=lanch.id,
        avaliacao_geral=6,
    ))
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_db_aceita_participacao_avaliacao_null(app):
    """avaliacao_geral=NULL eh valido (rodada ainda nao avaliada)."""
    rodada = Rodada.query.first()
    lanch = Lanchonete.query.first()
    db.session.add(ParticipacaoRodada(
        rodada_id=rodada.id, lanchonete_id=lanch.id,
        avaliacao_geral=None,
    ))
    db.session.commit()  # NAO levanta


# ---------- HTTP-level (rotas) ----------

def test_avaliar_estrelas_zero_rejeita(app, client_lanchA):
    """Rota /fluxo/.../avaliar com estrelas=0 deve rejeitar com flash."""
    rodada_id, lanch_id, _, _ = cenario_rodada_finalizada_com_aceite()
    # Setup: precisa ter pagamento + entrega + recebimento_ok pra avaliar
    p = ParticipacaoRodada.query.filter_by(
        rodada_id=rodada_id, lanchonete_id=lanch_id,
    ).first()
    p.recebimento_ok = True
    db.session.commit()

    csrf = _csrf(client_lanchA, f"/minhas-rodadas/{rodada_id}")
    r = client_lanchA.post(
        f"/fluxo/rodada/{rodada_id}/avaliar",
        data={"csrf_token": csrf, "estrelas": "0"},
        follow_redirects=False,
    )
    # Redireciona com flash error, NAO grava avaliacao
    assert r.status_code == 302
    p_after = db.session.get(ParticipacaoRodada, p.id)
    assert p_after.avaliacao_geral is None


def test_avaliar_estrelas_seis_rejeita(app, client_lanchA):
    rodada_id, lanch_id, _, _ = cenario_rodada_finalizada_com_aceite()
    p = ParticipacaoRodada.query.filter_by(
        rodada_id=rodada_id, lanchonete_id=lanch_id,
    ).first()
    p.recebimento_ok = True
    db.session.commit()

    csrf = _csrf(client_lanchA, f"/minhas-rodadas/{rodada_id}")
    r = client_lanchA.post(
        f"/fluxo/rodada/{rodada_id}/avaliar",
        data={"csrf_token": csrf, "estrelas": "6"},
        follow_redirects=False,
    )
    assert r.status_code == 302
    p_after = db.session.get(ParticipacaoRodada, p.id)
    assert p_after.avaliacao_geral is None
