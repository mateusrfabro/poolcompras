"""Testes do auto-save de itens do catalogo (lanchonete).

POST /pedidos/catalogo/auto-save aceita produto_id + quantidade e
atualiza/cria/remove apenas o ItemPedido daquele produto, retornando
JSON {ok, salvo_em}.
"""
import re
import json

from app import db
from app.models import ItemPedido, ParticipacaoRodada, Rodada, RodadaProduto


def _get_csrf(client, url):
    r = client.get(url)
    m = re.search(rb'name="csrf_token"[^>]*value="([^"]+)"', r.data)
    return m.group(1).decode() if m else ""


def _payload(produto_id, qtd, csrf):
    return {"csrf_token": csrf, "produto_id": str(produto_id), "quantidade": str(qtd)}


def test_auto_save_cria_item_quando_qtd_positiva(app, client_lanchA):
    csrf = _get_csrf(client_lanchA, "/pedidos/catalogo")
    rp = RodadaProduto.query.first()
    r = client_lanchA.post(
        "/pedidos/catalogo/auto-save",
        data=_payload(rp.produto_id, "5.5", csrf),
    )
    assert r.status_code == 200
    body = r.get_json()
    assert body["ok"] is True
    assert "salvo_em" in body

    item = ItemPedido.query.filter_by(produto_id=rp.produto_id).first()
    assert item is not None
    assert float(item.quantidade) == 5.5


def test_auto_save_atualiza_item_existente(app, client_lanchA):
    """Chamar 2x com qtds diferentes nao duplica — atualiza."""
    csrf = _get_csrf(client_lanchA, "/pedidos/catalogo")
    rp = RodadaProduto.query.first()
    client_lanchA.post(
        "/pedidos/catalogo/auto-save", data=_payload(rp.produto_id, "10", csrf),
    )
    client_lanchA.post(
        "/pedidos/catalogo/auto-save", data=_payload(rp.produto_id, "20", csrf),
    )
    items = ItemPedido.query.filter_by(produto_id=rp.produto_id).all()
    assert len(items) == 1
    assert float(items[0].quantidade) == 20.0


def test_auto_save_qtd_zero_remove_item(app, client_lanchA):
    csrf = _get_csrf(client_lanchA, "/pedidos/catalogo")
    rp = RodadaProduto.query.first()
    # Primeiro cria
    client_lanchA.post(
        "/pedidos/catalogo/auto-save", data=_payload(rp.produto_id, "3", csrf),
    )
    assert ItemPedido.query.filter_by(produto_id=rp.produto_id).count() == 1
    # Agora zera — deve remover
    r = client_lanchA.post(
        "/pedidos/catalogo/auto-save", data=_payload(rp.produto_id, "0", csrf),
    )
    assert r.status_code == 200
    assert r.get_json()["ok"] is True
    assert ItemPedido.query.filter_by(produto_id=rp.produto_id).count() == 0


def test_auto_save_produto_fora_do_catalogo_retorna_404(app, client_lanchA):
    csrf = _get_csrf(client_lanchA, "/pedidos/catalogo")
    r = client_lanchA.post(
        "/pedidos/catalogo/auto-save",
        data=_payload(99999, "1", csrf),
    )
    assert r.status_code == 404
    assert r.get_json()["ok"] is False


def test_auto_save_bloqueado_quando_pedido_aprovado(app, client_lanchA):
    """Apos admin aprovar pedido, lanchonete nao pode mais editar via auto-save."""
    from datetime import datetime, timezone
    from app.models import Lanchonete

    rp = RodadaProduto.query.first()
    rodada = Rodada.query.first()
    lanch = Lanchonete.query.filter_by(nome_fantasia="Lanch A").first()
    db.session.add(ParticipacaoRodada(
        rodada_id=rodada.id, lanchonete_id=lanch.id,
        pedido_enviado_em=datetime.now(timezone.utc),
        pedido_aprovado_em=datetime.now(timezone.utc),
    ))
    db.session.commit()

    csrf = _get_csrf(client_lanchA, "/pedidos/catalogo")
    r = client_lanchA.post(
        "/pedidos/catalogo/auto-save", data=_payload(rp.produto_id, "5", csrf),
    )
    assert r.status_code == 403
    assert r.get_json()["ok"] is False
