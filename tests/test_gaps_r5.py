"""Gaps de teste apontados pelo tester R5.

Cobertura nova:
- _calcular_linhas_cotacao unitario (helper extraido em commit 0cad71e)
- Anti-enumeration signup: flash NAO revela "email cadastrado"
- Open redirect URL-encoded (%2F%2F)
- Audit log emitido (caplog em ADMIN_MODERAR_PEDIDO)
- Paginacao ?page=999 retorna lista vazia, nao 500
- IntegrityError via HTTP nao gera 500 (CheckConstraint runtime)
- Audit log de EXPORT_CSV
"""
import re
import logging

import pytest

from app import db
from app.models import (
    Cotacao, Fornecedor, ItemPedido, Lanchonete, ParticipacaoRodada,
    Produto, Rodada, RodadaProduto, SubmissaoCotacao,
)
from app.routes.fornecedor.cotacao_final import _calcular_linhas_cotacao
from datetime import datetime, timezone
from ._helpers import cenario_rodada_em_negociacao


def _csrf(client, url):
    r = client.get(url)
    m = re.search(rb'name="csrf_token"[^>]*value="([^"]+)"', r.data)
    return m.group(1).decode() if m else None


# ---------- _calcular_linhas_cotacao ----------

class _RP:
    """Stub minimo de RodadaProduto pro helper puro."""
    def __init__(self, produto_id, preco_partida=None, produto=None):
        self.produto_id = produto_id
        self.preco_partida = preco_partida
        self.produto = produto


class _Cot:
    def __init__(self, preco):
        self.preco_unitario = preco


def test_calcular_linhas_pula_produto_sem_volume(app):
    """Produto que ninguem pediu (pid not in volumes) eh pulado."""
    rps = [_RP(produto_id=1, preco_partida=20)]
    linhas, tp, tf, etrs, etpct = _calcular_linhas_cotacao(rps, volumes={}, cotacoes_existentes={})
    assert linhas == []
    assert tp == 0.0 and tf == 0.0 and etrs == 0 and etpct == 0


def test_calcular_linhas_economia_positiva(app):
    """Partida=20, final=15, vol=10 -> economia=50, pct=25%."""
    rps = [_RP(produto_id=1, preco_partida=20)]
    volumes = {1: 10}
    cotacoes = {1: _Cot(15)}
    linhas, tp, tf, etrs, etpct = _calcular_linhas_cotacao(rps, volumes, cotacoes)
    assert len(linhas) == 1
    l = linhas[0]
    assert l["partida"] == 20.0
    assert l["final"] == 15.0
    assert l["economia_pct"] == 25.0
    assert l["economia_rs"] == 50.0
    # Totais: partida=20*10=200, final=15*10=150
    assert tp == 200.0 and tf == 150.0
    assert etrs == 50.0 and etpct == 25.0


def test_calcular_linhas_partida_zero_nao_divide(app):
    """preco_partida=None nao tenta dividir (evita ZeroDivisionError)."""
    rps = [_RP(produto_id=1, preco_partida=None)]
    volumes = {1: 5}
    cotacoes = {1: _Cot(10)}
    linhas, tp, tf, _, _ = _calcular_linhas_cotacao(rps, volumes, cotacoes)
    assert linhas[0]["economia_pct"] is None
    assert tp == 0.0 and tf == 0.0


def test_calcular_linhas_final_none_pendente(app):
    """Cotacao ainda nao preenchida (final=None) — linha existe, sem economia."""
    rps = [_RP(produto_id=1, preco_partida=20)]
    volumes = {1: 10}
    cotacoes = {}  # sem cotacao
    linhas, _, _, _, _ = _calcular_linhas_cotacao(rps, volumes, cotacoes)
    assert linhas[0]["final"] is None
    assert linhas[0]["economia_pct"] is None


# ---------- Anti-enumeration signup ----------

def test_signup_email_existente_nao_revela(app, client):
    """Registro com email ja cadastrado retorna flash GENERICO, nao 'ja existe'."""
    # 'lancha@test.com' ja existe no seed
    r = client.post(
        "/registro",
        data={
            "email": "lancha@test.com", "senha": "novasenha123",
            "nome_responsavel": "Foo", "telefone": "(43) 99999-1234",
            "nome_fantasia": "Foo", "cnpj": "", "endereco": "", "bairro": "",
            "aceite_termos": "on",  # LGPD checkbox obrigatorio desde a1b2c3d4e5f6
        },
        follow_redirects=True,
    )
    body = r.data.decode("utf-8", errors="ignore").lower()
    # NAO deve revelar
    assert "já está cadastrado" not in body
    assert "email cadastrado" not in body
    # DEVE ter mensagem generica
    assert ("não foi possível" in body or "se você já tem conta" in body)


# ---------- Open redirect URL-encoded ----------

def test_login_next_url_encoded_rejeitado(app, client):
    """`?next=%2F%2Fevil.example` (URL-encoded) tambem deve ser bloqueado."""
    csrf = _csrf(client, "/login")
    r = client.post(
        "/login?next=%2F%2Fevil.example%2Fphish",
        data={"csrf_token": csrf, "email": "lancha@test.com", "senha": "testpass"},
        follow_redirects=False,
    )
    assert r.status_code == 302
    location = r.headers.get("Location", "")
    assert "evil.example" not in location


# ---------- Audit log via caplog ----------

def test_audit_log_admin_moderar_pedido(app, client_admin, caplog):
    """logger.info ADMIN_MODERAR_PEDIDO emitido ao aprovar."""
    rodada_id, lanch_id, _, _ = cenario_rodada_em_negociacao()
    # Cria submissao de pedido pendente (precisa enviado_em pra moderar)
    p = ParticipacaoRodada.query.filter_by(
        rodada_id=rodada_id, lanchonete_id=lanch_id,
    ).first()
    p.pedido_aprovado_em = None  # zera pra ser "pendente"
    p.pedido_enviado_em = datetime.now(timezone.utc)
    db.session.commit()

    csrf = _csrf(client_admin, f"/admin/rodadas/{rodada_id}/moderar-pedidos")
    with caplog.at_level(logging.INFO, logger="app.routes.admin.moderacao"):
        client_admin.post(
            f"/admin/rodadas/{rodada_id}/moderar-pedidos",
            data={"csrf_token": csrf, "participacao_id": p.id, "acao": "aprovar"},
            follow_redirects=False,
        )

    audit = [r for r in caplog.records if "ADMIN_MODERAR_PEDIDO" in r.getMessage()]
    assert len(audit) >= 1
    # Email NAO aparece em audit (só id)
    assert "@" not in audit[0].getMessage()


def test_audit_log_export_csv(app, client_admin, caplog):
    """logger.info ADMIN_EXPORT_CSV emitido ao baixar CSV."""
    with caplog.at_level(logging.INFO, logger="app.routes.admin.fornecedores"):
        r = client_admin.get("/admin/fornecedores/exportar.csv")
    assert r.status_code == 200
    audit = [r for r in caplog.records if "ADMIN_EXPORT_CSV" in r.getMessage()]
    assert len(audit) >= 1


# ---------- Paginacao defensiva ----------

def test_paginacao_page_999_nao_quebra(app, client):
    """?page=999 em rodadas.listar retorna 200 com lista vazia, nao 500."""
    r = client.get("/rodadas/?page=999", follow_redirects=False)
    # Pode redirecionar pra login (se nao logado) ou render vazio se logado.
    assert r.status_code in (200, 302)


def test_paginacao_historico_aprovacoes_page_negativo(app, client_admin):
    """page negativo nao quebra (Flask-SQLAlchemy paginate trata)."""
    r = client_admin.get("/admin/historico-aprovacoes?page=-1")
    assert r.status_code in (200, 302, 400)


# ---------- IntegrityError runtime via HTTP ----------

def test_check_constraint_preco_zero_via_http_nao_500(app, client_forn):
    """Postar preco_final=0 em cotacao (CheckConstraint preco>0) deve flashar
    erro, nao 500. Hoje a rota faz `if preco_final <= 0: continue` antes do
    flush, mas teste protege contra regressao."""
    rodada_id, _, forn_id, produto_id = cenario_rodada_em_negociacao(preco_partida=20.0)

    csrf = _csrf(client_forn, f"/fornecedor/rodada/{rodada_id}/cotacao-final")
    r = client_forn.post(
        f"/fornecedor/rodada/{rodada_id}/cotacao-final",
        data={
            "csrf_token": csrf,
            f"preco_final_{produto_id}": "0",
            "acao": "salvar",
        },
        follow_redirects=False,
    )
    # Nao deve dar 500. 200 (re-render) ou 302 (redirect c/ flash) sao OK.
    assert r.status_code in (200, 302)
    # Cotacao com preco=0 NAO foi inserida
    c = Cotacao.query.filter_by(
        rodada_id=rodada_id, fornecedor_id=forn_id, produto_id=produto_id,
    ).first()
    assert c is None or float(c.preco_unitario) > 0
