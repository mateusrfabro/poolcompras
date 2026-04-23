"""Testes E2E do fluxo etapas 1-4 (gap identificado pelo tester).

Cobre transicoes iniciais da rodada:
1. Admin cria rodada (POST /admin/rodadas/nova) -> status=preparando
2. Admin monta catalogo + envia (POST /admin/rodadas/<id>/catalogo acao=enviar)
   -> status=aguardando_cotacao
3. Fornecedor coloca preco de partida (POST /fornecedor/rodada/<id>/cotar-catalogo)
4. Se todos produtos tem partida + nenhum pendente -> rodada.status=aberta
"""
import re

from app import db
from app.models import Rodada, RodadaProduto, Produto


def _csrf(client, url):
    r = client.get(url)
    m = re.search(rb'name="csrf_token"[^>]*value="([^"]+)"', r.data)
    return m.group(1).decode() if m else None


# ---------- Etapa 1: admin cria rodada ----------

def test_admin_cria_rodada_com_status_preparando(app, client_admin):
    token = _csrf(client_admin, "/admin/rodadas/nova")
    r = client_admin.post(
        "/admin/rodadas/nova",
        data={
            "csrf_token": token,
            "nome": "Rodada E2E",
            "data_abertura": "2026-04-24",
            "data_fechamento": "2026-04-30",
        },
        follow_redirects=False,
    )
    assert r.status_code == 302
    rodada = Rodada.query.filter_by(nome="Rodada E2E").first()
    assert rodada is not None
    assert rodada.status == "preparando"


def test_lanchonete_nao_cria_rodada(app, client_lanchA):
    r = client_lanchA.post(
        "/admin/rodadas/nova",
        data={"nome": "X", "data_abertura": "2026-04-24",
              "data_fechamento": "2026-04-30"},
        follow_redirects=False,
    )
    assert r.status_code == 302
    assert Rodada.query.filter_by(nome="X").first() is None


# ---------- Etapa 2: admin monta catalogo + envia ----------

def test_admin_envia_catalogo_muda_status_aguardando_cotacao(app, client_admin):
    # Cria rodada em preparando
    r0 = Rodada(nome="Catalogo Test",
                data_abertura=db.func.datetime(),
                data_fechamento=db.func.datetime(),
                status="preparando")
    db.session.add(r0)
    db.session.commit()
    r_id = r0.id

    produto = Produto.query.first()
    token = _csrf(client_admin, f"/admin/rodadas/{r_id}/catalogo")
    r = client_admin.post(
        f"/admin/rodadas/{r_id}/catalogo",
        data={
            "csrf_token": token,
            "produto_id": str(produto.id),
            "acao": "enviar",
        },
        follow_redirects=False,
    )
    assert r.status_code == 302
    rodada = db.session.get(Rodada, r_id)
    assert rodada.status == "aguardando_cotacao"
    rps = RodadaProduto.query.filter_by(rodada_id=r_id).all()
    assert len(rps) == 1
    assert rps[0].produto_id == produto.id


def test_admin_salva_catalogo_sem_enviar_mantem_preparando(app, client_admin):
    """Acao 'salvar' (nao 'enviar') mantem status=preparando."""
    r0 = Rodada(nome="Salvar Test",
                data_abertura=db.func.datetime(),
                data_fechamento=db.func.datetime(),
                status="preparando")
    db.session.add(r0)
    db.session.commit()
    r_id = r0.id

    produto = Produto.query.first()
    token = _csrf(client_admin, f"/admin/rodadas/{r_id}/catalogo")
    client_admin.post(
        f"/admin/rodadas/{r_id}/catalogo",
        data={
            "csrf_token": token,
            "produto_id": str(produto.id),
            "acao": "salvar",
        },
    )
    assert db.session.get(Rodada, r_id).status == "preparando"


# ---------- Etapa 3: fornecedor coloca preco de partida ----------

def test_fornecedor_preenche_preco_partida_libera_rodada(app, client_forn):
    """Todos produtos com preco_partida + nenhum pendente => rodada.status=aberta."""
    # Setup: rodada em aguardando_cotacao com 1 produto (do catalogo do admin)
    rodada = Rodada.query.first()
    rodada.status = "aguardando_cotacao"
    produto = Produto.query.first()
    # Ja existe RodadaProduto no seed; so garante sem preco
    rp = RodadaProduto.query.filter_by(rodada_id=rodada.id, produto_id=produto.id).first()
    rp.preco_partida = None
    db.session.commit()
    r_id = rodada.id
    rp_id = rp.id

    token = _csrf(client_forn, f"/fornecedor/rodada/{r_id}/cotar-catalogo")
    r = client_forn.post(
        f"/fornecedor/rodada/{r_id}/cotar-catalogo",
        data={
            "csrf_token": token,
            f"preco_{rp_id}": "15.50",
        },
        follow_redirects=False,
    )
    assert r.status_code == 302

    # Preco salvo + rodada liberada (status=aberta)
    rp_after = db.session.get(RodadaProduto, rp_id)
    assert float(rp_after.preco_partida) == 15.50
    assert db.session.get(Rodada, r_id).status == "aberta"


def test_fornecedor_sugere_produto_novo_fica_inativo(app, client_forn):
    """Regressao: produto sugerido nasce ativo=False (nao polui catalogo global).

    Espelho de test_regressao_produto_sugerido.py mas via HTTP real.
    """
    rodada = Rodada.query.first()
    rodada.status = "aguardando_cotacao"
    db.session.commit()
    r_id = rodada.id

    token = _csrf(client_forn, f"/fornecedor/rodada/{r_id}/cotar-catalogo")
    client_forn.post(
        f"/fornecedor/rodada/{r_id}/cotar-catalogo",
        data={
            "csrf_token": token,
            "novo_nome": "Cheddar Artesanal",
            "novo_categoria": "Queijo",
            "novo_subcategoria": "Fatiado",
            "novo_unidade": "kg",
            "novo_preco": "42.00",
        },
        follow_redirects=False,
    )

    p = Produto.query.filter_by(nome="Cheddar Artesanal").first()
    assert p is not None
    assert p.ativo is False, "Produto sugerido NAO pode nascer ativo no catalogo global"
    # RodadaProduto criado com aprovado=None
    rp = RodadaProduto.query.filter_by(rodada_id=r_id, produto_id=p.id).first()
    assert rp is not None
    assert rp.aprovado is None


def test_lanchonete_nao_acessa_cotar_catalogo(app, client_lanchA):
    rodada = Rodada.query.first()
    rodada.status = "aguardando_cotacao"
    db.session.commit()

    r = client_lanchA.get(f"/fornecedor/rodada/{rodada.id}/cotar-catalogo",
                           follow_redirects=False)
    assert r.status_code == 302  # redirect pro dashboard (fornecedor_required)


def test_fornecedor_nao_cota_rodada_status_errado(app, client_forn):
    """Rodada em 'preparando' ainda nao aceita cotacao de partida."""
    rodada = Rodada.query.first()
    rodada.status = "preparando"
    db.session.commit()

    r = client_forn.post(
        f"/fornecedor/rodada/{rodada.id}/cotar-catalogo",
        data={},
        follow_redirects=False,
    )
    # Nao e aguardando_cotacao, entao redireciona pro dashboard
    assert r.status_code == 302
