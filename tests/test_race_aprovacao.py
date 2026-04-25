"""Race tests: tentativa de criar 2 cotacoes vencedoras pro mesmo
(rodada, produto) deve falhar pelo unique partial index criado em
migration a5b6c7d8e903 (ix_cotacao_vencedora_unica WHERE selecionada IS TRUE).

Esses tests garantem que a constraint do DB protege a invariante "1 vencedora
por rodada×produto" mesmo se houver erro logico no app que tente burlar.
"""
import pytest
from sqlalchemy.exc import IntegrityError

from app import db
from app.models import Cotacao, Fornecedor, Produto, Rodada, Usuario
from werkzeug.security import generate_password_hash


def test_unique_partial_bloqueia_duas_vencedoras(app):
    """Insert direto de 2 Cotacao(selecionada=True) pro mesmo produto+rodada
    deve quebrar com IntegrityError pelo partial unique index."""
    rodada = Rodada.query.first()
    produto = Produto.query.first()
    fA = Fornecedor.query.first()

    # Cria forn B
    uB = Usuario(email="raceb@test.com",
                 senha_hash=generate_password_hash("tp"),
                 nome_responsavel="B", telefone="", tipo="fornecedor")
    db.session.add(uB)
    db.session.flush()
    fB = Fornecedor(usuario_id=uB.id, razao_social="Fornec Race B")
    db.session.add(fB)
    db.session.flush()

    # 1a vencedora — passa
    db.session.add(Cotacao(
        rodada_id=rodada.id, fornecedor_id=fA.id,
        produto_id=produto.id, preco_unitario=10, selecionada=True,
    ))
    db.session.commit()

    # 2a vencedora pro MESMO produto+rodada (forn diferente) — DEVE QUEBRAR
    db.session.add(Cotacao(
        rodada_id=rodada.id, fornecedor_id=fB.id,
        produto_id=produto.id, preco_unitario=8, selecionada=True,
    ))
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_unique_partial_permite_nao_vencedoras(app):
    """Multiplas Cotacao(selecionada=False) pro mesmo (rodada,produto) sao OK
    — partial index so vincula quando selecionada=True."""
    rodada = Rodada.query.first()
    produto = Produto.query.first()
    fA = Fornecedor.query.first()

    uB = Usuario(email="raceb2@test.com",
                 senha_hash=generate_password_hash("tp"),
                 nome_responsavel="B", telefone="", tipo="fornecedor")
    db.session.add(uB)
    db.session.flush()
    fB = Fornecedor(usuario_id=uB.id, razao_social="Fornec Race B2")
    db.session.add(fB)
    db.session.flush()

    db.session.add(Cotacao(
        rodada_id=rodada.id, fornecedor_id=fA.id,
        produto_id=produto.id, preco_unitario=10, selecionada=False,
    ))
    db.session.add(Cotacao(
        rodada_id=rodada.id, fornecedor_id=fB.id,
        produto_id=produto.id, preco_unitario=8, selecionada=False,
    ))
    db.session.commit()  # NAO levanta — selecionada=False nao entra no partial


def test_unique_constraint_uma_cotacao_por_fornecedor(app):
    """uq_cotacao_rodada_fornecedor_produto: mesmo fornecedor nao envia 2
    cotacoes pro mesmo produto na mesma rodada (independente de selecionada)."""
    rodada = Rodada.query.first()
    produto = Produto.query.first()
    fA = Fornecedor.query.first()

    db.session.add(Cotacao(
        rodada_id=rodada.id, fornecedor_id=fA.id,
        produto_id=produto.id, preco_unitario=10,
    ))
    db.session.commit()

    db.session.add(Cotacao(
        rodada_id=rodada.id, fornecedor_id=fA.id,
        produto_id=produto.id, preco_unitario=12,
    ))
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()
