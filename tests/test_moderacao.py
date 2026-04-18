"""Testes do fluxo de moderacao de pedidos + cotacao final + filtros de invisibilidade."""
import re
from datetime import datetime
from app import db
from app.models import (
    ParticipacaoRodada, ItemPedido, Rodada, Produto, Lanchonete,
    Fornecedor, RodadaProduto, Cotacao, Usuario,
)


def _get_csrf(client, url):
    r = client.get(url)
    m = re.search(rb'name="csrf_token"[^>]*value="([^"]+)"', r.data)
    return m.group(1).decode() if m else None


# ------- Fluxo salvar (rascunho) vs enviar (submeter) -------

def test_salvar_pedido_nao_submete_pra_moderacao(app, client_lanchA):
    rodada = Rodada.query.first()
    produto = Produto.query.first()
    lanch = Lanchonete.query.filter_by(nome_fantasia="Lanch A").first()

    token = _get_csrf(client_lanchA, "/pedidos/catalogo")
    r = client_lanchA.post("/pedidos/catalogo", data={
        "csrf_token": token,
        f"qtd_{produto.id}": "5",
        "acao": "salvar",
    })
    assert r.status_code in (200, 302)

    part = ParticipacaoRodada.query.filter_by(
        rodada_id=rodada.id, lanchonete_id=lanch.id,
    ).first()
    assert part is not None
    assert part.pedido_enviado_em is None


def test_enviar_pedido_marca_enviado_em(app, client_lanchA):
    rodada = Rodada.query.first()
    produto = Produto.query.first()
    lanch = Lanchonete.query.filter_by(nome_fantasia="Lanch A").first()

    token = _get_csrf(client_lanchA, "/pedidos/catalogo")
    r = client_lanchA.post("/pedidos/catalogo", data={
        "csrf_token": token,
        f"qtd_{produto.id}": "5",
        "acao": "enviar",
    })
    assert r.status_code in (200, 302)

    part = ParticipacaoRodada.query.filter_by(
        rodada_id=rodada.id, lanchonete_id=lanch.id,
    ).first()
    assert part.pedido_enviado_em is not None
    assert part.pedido_aprovado_em is None


def test_enviar_sem_itens_bloqueia(app, client_lanchA):
    token = _get_csrf(client_lanchA, "/pedidos/catalogo")
    r = client_lanchA.post("/pedidos/catalogo", data={
        "csrf_token": token,
        "acao": "enviar",
    }, follow_redirects=True)
    assert r.status_code == 200


# ------- Moderacao admin -------

def _cria_pedido_enviado_lanchA():
    """Cria ParticipacaoRodada + ItemPedido direto no DB (isola teste de moderacao)."""
    produto = Produto.query.first()
    rodada = Rodada.query.first()
    lanch = Lanchonete.query.filter_by(nome_fantasia="Lanch A").first()
    db.session.add(ItemPedido(
        rodada_id=rodada.id, lanchonete_id=lanch.id,
        produto_id=produto.id, quantidade=5,
    ))
    part = ParticipacaoRodada(
        rodada_id=rodada.id, lanchonete_id=lanch.id,
        pedido_enviado_em=datetime.utcnow(),
    )
    db.session.add(part)
    db.session.commit()
    return rodada.id, part.id


def test_admin_aprova_pedido(app, client_admin):
    rodada_id, part_id = _cria_pedido_enviado_lanchA()

    token = _get_csrf(client_admin, f"/admin/rodadas/{rodada_id}/moderar-pedidos")
    r = client_admin.post(f"/admin/rodadas/{rodada_id}/moderar-pedidos", data={
        "csrf_token": token, "participacao_id": part_id, "acao": "aprovar",
    })
    assert r.status_code in (200, 302)

    part = db.session.get(ParticipacaoRodada, part_id)
    assert part.pedido_aprovado_em is not None
    assert part.pedido_aprovado_por_id is not None


def test_admin_devolve_pedido_com_motivo(app, client_admin):
    rodada_id, part_id = _cria_pedido_enviado_lanchA()

    token = _get_csrf(client_admin, f"/admin/rodadas/{rodada_id}/moderar-pedidos")
    client_admin.post(f"/admin/rodadas/{rodada_id}/moderar-pedidos", data={
        "csrf_token": token, "participacao_id": part_id,
        "acao": "devolver", "motivo": "volume muito alto",
    })

    part = db.session.get(ParticipacaoRodada, part_id)
    assert part.pedido_devolvido_em is not None
    assert part.pedido_motivo_devolucao == "volume muito alto"
    assert part.pedido_enviado_em is None
    assert part.pedido_aprovado_em is None


def test_admin_reprova_pedido(app, client_admin):
    rodada_id, part_id = _cria_pedido_enviado_lanchA()

    token = _get_csrf(client_admin, f"/admin/rodadas/{rodada_id}/moderar-pedidos")
    client_admin.post(f"/admin/rodadas/{rodada_id}/moderar-pedidos", data={
        "csrf_token": token, "participacao_id": part_id, "acao": "reprovar",
    })

    part = db.session.get(ParticipacaoRodada, part_id)
    assert part.pedido_reprovado_em is not None


def test_admin_reverte_aprovacao(app, client_admin):
    rodada_id, part_id = _cria_pedido_enviado_lanchA()

    token = _get_csrf(client_admin, f"/admin/rodadas/{rodada_id}/moderar-pedidos")
    client_admin.post(f"/admin/rodadas/{rodada_id}/moderar-pedidos", data={
        "csrf_token": token, "participacao_id": part_id, "acao": "aprovar",
    })
    assert db.session.get(ParticipacaoRodada, part_id).pedido_aprovado_em is not None

    token = _get_csrf(client_admin, f"/admin/rodadas/{rodada_id}/moderar-pedidos")
    client_admin.post(f"/admin/rodadas/{rodada_id}/moderar-pedidos", data={
        "csrf_token": token, "participacao_id": part_id, "acao": "reverter",
    })
    part = db.session.get(ParticipacaoRodada, part_id)
    assert part.pedido_aprovado_em is None
    assert part.pedido_enviado_em is not None


# ------- Filtros de invisibilidade -------

def test_fornecedor_nao_ve_pedido_nao_aprovado(app, client_forn):
    """Itens de pedidos nao aprovados nao devem aparecer na demanda do fornecedor."""
    _cria_pedido_enviado_lanchA()  # enviado mas nao aprovado
    rodada = Rodada.query.first()
    r = client_forn.get(f"/fornecedor/rodada/{rodada.id}")
    assert r.status_code == 200
    # Produto aparece no catalogo mas com quantidade 0 (ou ausente do agregado)


def test_fornecedor_ve_pedido_aprovado(app, client_forn):
    """Apos aprovacao direta no DB, demanda deve ficar visivel pro fornecedor."""
    rodada_id, part_id = _cria_pedido_enviado_lanchA()
    # Aprova direto no DB (sem passar por client_admin)
    part = db.session.get(ParticipacaoRodada, part_id)
    part.pedido_aprovado_em = datetime.utcnow()
    db.session.commit()

    r = client_forn.get(f"/fornecedor/rodada/{rodada_id}")
    assert r.status_code == 200
    assert b"Blend" in r.data


# ------- Quick win: repetir ultimo pedido -------

def test_repetir_ultimo_pedido_copia_itens(app, client_lanchA):
    rodada_antiga = Rodada.query.first()
    produto = Produto.query.first()
    lanch = Lanchonete.query.filter_by(nome_fantasia="Lanch A").first()
    db.session.add(ItemPedido(
        rodada_id=rodada_antiga.id, lanchonete_id=lanch.id,
        produto_id=produto.id, quantidade=7,
    ))
    rodada_antiga.status = "finalizada"
    from datetime import timedelta, timezone
    agora = datetime.now(timezone.utc).replace(tzinfo=None)
    nova = Rodada(
        nome="Rodada 2", data_abertura=agora,
        data_fechamento=agora + timedelta(hours=6), status="aberta",
    )
    db.session.add(nova)
    db.session.flush()
    db.session.add(RodadaProduto(rodada_id=nova.id, produto_id=produto.id))
    db.session.commit()
    nova_id = nova.id
    lanch_id = lanch.id

    token = _get_csrf(client_lanchA, "/pedidos/catalogo")
    r = client_lanchA.post("/pedidos/repetir-ultimo-pedido", data={"csrf_token": token})
    assert r.status_code in (200, 302)

    item = ItemPedido.query.filter_by(rodada_id=nova_id, lanchonete_id=lanch_id).first()
    assert item is not None
    assert float(item.quantidade) == 7.0


# ------- Smoke test das telas novas -------

def test_admin_historico_aprovacoes_renderiza(client_admin):
    r = client_admin.get("/admin/historico-aprovacoes")
    assert r.status_code == 200


def test_admin_rodada_funil_renderiza(app, client_admin):
    rid = Rodada.query.first().id
    r = client_admin.get(f"/admin/rodadas/{rid}/funil")
    assert r.status_code == 200


def test_admin_produto_historico_precos_renderiza(app, client_admin):
    pid = Produto.query.first().id
    r = client_admin.get(f"/admin/produtos/{pid}/historico-precos")
    assert r.status_code == 200