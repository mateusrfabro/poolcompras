"""Testes dos hooks de notificacao no admin/moderacao.py — confirma que cada
acao (aprovar/devolver/reverter) dispara EXATAMENTE as notificacoes esperadas
e respeita guard de idempotencia + isolamento por rodada.

Cobre 4 gaps identificados pos-commit dos hooks Telegram:
1. Aprovar dispara notif do fornecedor + lanchonetes. Aprovar de novo (idempotente)
   nao dispara nada.
2. Devolver dispara notif so do fornecedor (lanchonetes nao recebem ruido).
3. Reverter NAO dispara notif nenhuma — explicita pra evitar regressao.
4. submissao_id de outra rodada nao eh aceito (guarda 'sub.rodada_id != rodada_id').
"""
import os
import re
from datetime import datetime, timezone
from unittest.mock import patch
from werkzeug.security import generate_password_hash

from app import db
from app.models import (
    Usuario, Fornecedor, Lanchonete, Rodada, Produto, RodadaProduto,
    SubmissaoCotacao, ItemPedido, ParticipacaoRodada, Cotacao,
)


def _get_csrf(client, url):
    r = client.get(url)
    m = re.search(rb'name="csrf_token"[^>]*value="([^"]+)"', r.data)
    return m.group(1).decode() if m else None


def _seed_em_negociacao_com_pedido():
    """Prepara cenario: rodada em_negociacao, lanchonete A pediu, fornecedor com submissao."""
    rodada = Rodada.query.first()
    produto = Produto.query.first()
    lanch = Lanchonete.query.filter_by(nome_fantasia="Lanch A").first()
    forn = Fornecedor.query.first()

    db.session.add(ItemPedido(
        rodada_id=rodada.id, lanchonete_id=lanch.id,
        produto_id=produto.id, quantidade=10,
    ))
    db.session.add(ParticipacaoRodada(
        rodada_id=rodada.id, lanchonete_id=lanch.id,
        pedido_enviado_em=datetime.now(timezone.utc),
        pedido_aprovado_em=datetime.now(timezone.utc),
    ))
    sub = SubmissaoCotacao(
        rodada_id=rodada.id, fornecedor_id=forn.id,
        enviada_em=datetime.now(timezone.utc),
    )
    db.session.add(sub)
    rodada.status = "em_negociacao"
    db.session.commit()
    return rodada.id, sub.id, lanch, forn


def _vincula_chat_ids():
    """Marca chat_id em fornecedor + lanchonete A pra forcar tentativa de envio."""
    for email, cid in (("forn@test.com", 9001), ("lancha@test.com", 9002)):
        u = Usuario.query.filter_by(email=email).first()
        u.telegram_chat_id = cid
    db.session.commit()


def test_aprovar_dispara_notif_fornecedor_e_lanchonete(app, client_admin):
    """Acao=aprovar manda 1 notif pro fornecedor + 1 pra cada lanchonete que pediu."""
    rodada_id, sub_id, _, _ = _seed_em_negociacao_com_pedido()
    _vincula_chat_ids()
    os.environ["TELEGRAM_BOT_TOKEN"] = "x"
    try:
        with patch("app.services.notificacoes.requests.post") as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {"ok": True}
            token = _get_csrf(client_admin, f"/admin/rodadas/{rodada_id}/aprovar-cotacoes")
            r = client_admin.post(
                f"/admin/rodadas/{rodada_id}/aprovar-cotacoes",
                data={"csrf_token": token, "submissao_id": sub_id, "acao": "aprovar"},
                follow_redirects=False,
            )
            assert r.status_code == 302
        # 1 notif pro fornecedor + 1 notif pra Lanch A (unica que pediu) = 2
        assert mock_post.call_count == 2
        textos = [c.kwargs["json"]["text"] for c in mock_post.call_args_list]
        # Uma mensagem fala "Cotação aprovada" (vai pro fornecedor)
        # Outra fala "Proposta de fornecedor" (vai pra lanchonete)
        assert any("Cotação aprovada" in t for t in textos)
        assert any("Proposta de fornecedor" in t for t in textos)
    finally:
        os.environ.pop("TELEGRAM_BOT_TOKEN", None)


def test_aprovar_idempotente_nao_dispara_notif_repetida(app, client_admin):
    """2 cliques no Aprovar: segundo retorna sem mutar nem notificar."""
    rodada_id, sub_id, _, _ = _seed_em_negociacao_com_pedido()
    _vincula_chat_ids()
    os.environ["TELEGRAM_BOT_TOKEN"] = "x"
    try:
        with patch("app.services.notificacoes.requests.post") as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {"ok": True}
            token = _get_csrf(client_admin, f"/admin/rodadas/{rodada_id}/aprovar-cotacoes")
            # 1o aprovar
            client_admin.post(
                f"/admin/rodadas/{rodada_id}/aprovar-cotacoes",
                data={"csrf_token": token, "submissao_id": sub_id, "acao": "aprovar"},
                follow_redirects=False,
            )
            chamadas_apos_1 = mock_post.call_count
            # 2o aprovar (idempotente)
            client_admin.post(
                f"/admin/rodadas/{rodada_id}/aprovar-cotacoes",
                data={"csrf_token": token, "submissao_id": sub_id, "acao": "aprovar"},
                follow_redirects=False,
            )
            chamadas_apos_2 = mock_post.call_count
        assert chamadas_apos_1 == 2  # forn + 1 lanch
        assert chamadas_apos_2 == 2  # NAO duplicou
    finally:
        os.environ.pop("TELEGRAM_BOT_TOKEN", None)


def test_devolver_notifica_so_fornecedor_nao_lanchonete(app, client_admin):
    """Acao=devolver: fornecedor recebe 'Cotação devolvida'; lanchonete NAO recebe nada
    (evita ruido — devolucao eh negociacao interna admin<->fornecedor)."""
    rodada_id, sub_id, _, _ = _seed_em_negociacao_com_pedido()
    _vincula_chat_ids()
    os.environ["TELEGRAM_BOT_TOKEN"] = "x"
    try:
        with patch("app.services.notificacoes.requests.post") as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {"ok": True}
            token = _get_csrf(client_admin, f"/admin/rodadas/{rodada_id}/aprovar-cotacoes")
            client_admin.post(
                f"/admin/rodadas/{rodada_id}/aprovar-cotacoes",
                data={"csrf_token": token, "submissao_id": sub_id, "acao": "devolver"},
                follow_redirects=False,
            )
        assert mock_post.call_count == 1  # so o fornecedor
        texto = mock_post.call_args.kwargs["json"]["text"]
        assert "Cotação devolvida" in texto
    finally:
        os.environ.pop("TELEGRAM_BOT_TOKEN", None)


def test_reverter_aprovacao_nao_dispara_notif(app, client_admin):
    """Acao=reverter remove aprovada_em sem disparar nenhuma notif. Sao
    operacoes administrativas que ja foram comunicadas — re-notificar gera
    confusao."""
    rodada_id, sub_id, _, _ = _seed_em_negociacao_com_pedido()
    # Pre-aprova a submissao pra simular cenario "ja foi aprovada"
    sub = db.session.get(SubmissaoCotacao, sub_id)
    sub.aprovada_em = datetime.now(timezone.utc)
    db.session.commit()

    _vincula_chat_ids()
    os.environ["TELEGRAM_BOT_TOKEN"] = "x"
    try:
        with patch("app.services.notificacoes.requests.post") as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {"ok": True}
            token = _get_csrf(client_admin, f"/admin/rodadas/{rodada_id}/aprovar-cotacoes")
            client_admin.post(
                f"/admin/rodadas/{rodada_id}/aprovar-cotacoes",
                data={"csrf_token": token, "submissao_id": sub_id, "acao": "reverter"},
                follow_redirects=False,
            )
        assert mock_post.call_count == 0
        # E a aprovacao foi REVERTIDA no DB
        assert db.session.get(SubmissaoCotacao, sub_id).aprovada_em is None
    finally:
        os.environ.pop("TELEGRAM_BOT_TOKEN", None)


def test_devolver_idempotente_nao_duplica_notif(app, client_admin):
    """2 cliques no Devolver sem reenvio do fornecedor: segundo retorna sem
    mutar nem disparar notif. Guard 'sub.devolvida_em is not None and
    sub.enviada_em is None'."""
    rodada_id, sub_id, _, _ = _seed_em_negociacao_com_pedido()
    _vincula_chat_ids()
    os.environ["TELEGRAM_BOT_TOKEN"] = "x"
    try:
        with patch("app.services.notificacoes.requests.post") as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {"ok": True}
            token = _get_csrf(client_admin, f"/admin/rodadas/{rodada_id}/aprovar-cotacoes")
            client_admin.post(
                f"/admin/rodadas/{rodada_id}/aprovar-cotacoes",
                data={"csrf_token": token, "submissao_id": sub_id, "acao": "devolver"},
                follow_redirects=False,
            )
            chamadas_apos_1 = mock_post.call_count
            client_admin.post(
                f"/admin/rodadas/{rodada_id}/aprovar-cotacoes",
                data={"csrf_token": token, "submissao_id": sub_id, "acao": "devolver"},
                follow_redirects=False,
            )
            chamadas_apos_2 = mock_post.call_count
        assert chamadas_apos_1 == 1
        assert chamadas_apos_2 == 1  # NAO duplicou
    finally:
        os.environ.pop("TELEGRAM_BOT_TOKEN", None)


def test_reverter_sem_aprovacao_nao_dispara_e_nao_muda(app, client_admin):
    """Reverter quando aprovada_em is None: retorna sem mutar — guard nova."""
    rodada_id, sub_id, _, _ = _seed_em_negociacao_com_pedido()
    sub_antes = db.session.get(SubmissaoCotacao, sub_id)
    enviada_em_antes = sub_antes.enviada_em

    os.environ["TELEGRAM_BOT_TOKEN"] = "x"
    try:
        with patch("app.services.notificacoes.requests.post") as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {"ok": True}
            token = _get_csrf(client_admin, f"/admin/rodadas/{rodada_id}/aprovar-cotacoes")
            client_admin.post(
                f"/admin/rodadas/{rodada_id}/aprovar-cotacoes",
                data={"csrf_token": token, "submissao_id": sub_id, "acao": "reverter"},
                follow_redirects=False,
            )
        assert mock_post.call_count == 0
        # Estado nao mudou
        sub_depois = db.session.get(SubmissaoCotacao, sub_id)
        assert sub_depois.aprovada_em is None
        assert sub_depois.enviada_em == enviada_em_antes
    finally:
        os.environ.pop("TELEGRAM_BOT_TOKEN", None)


def test_submissao_de_outra_rodada_rejeitada(app, client_admin):
    """Rota /admin/rodadas/<rodada_id>/aprovar-cotacoes deve recusar submissao_id
    que pertence a OUTRA rodada — guard sub.rodada_id != rodada_id."""
    rodada_id_a, sub_id_a, _, _ = _seed_em_negociacao_com_pedido()

    # Cria rodada B + submissao em B
    rodada_b = Rodada(
        nome="Rodada B",
        data_abertura=datetime.now(timezone.utc),
        data_fechamento=datetime.now(timezone.utc),
        status="em_negociacao",
    )
    db.session.add(rodada_b)
    db.session.flush()
    sub_b = SubmissaoCotacao(
        rodada_id=rodada_b.id,
        fornecedor_id=Fornecedor.query.first().id,
        enviada_em=datetime.now(timezone.utc),
    )
    db.session.add(sub_b)
    db.session.commit()
    sub_b_id = sub_b.id

    token = _get_csrf(client_admin, f"/admin/rodadas/{rodada_id_a}/aprovar-cotacoes")
    # Tenta aprovar sub_b passando rodada_id de A na URL
    client_admin.post(
        f"/admin/rodadas/{rodada_id_a}/aprovar-cotacoes",
        data={"csrf_token": token, "submissao_id": sub_b_id, "acao": "aprovar"},
        follow_redirects=False,
    )
    # Submissao B continua nao aprovada
    assert db.session.get(SubmissaoCotacao, sub_b_id).aprovada_em is None


# =============================================================================
# moderar_pedidos: hooks + guards de idempotencia em devolver/reprovar/reverter
# =============================================================================

def _seed_pedido_pendente():
    """Cria ParticipacaoRodada com pedido_enviado_em (pronto pra moderacao)."""
    rodada = Rodada.query.first()
    produto = Produto.query.first()
    lanch = Lanchonete.query.filter_by(nome_fantasia="Lanch A").first()
    db.session.add(ItemPedido(
        rodada_id=rodada.id, lanchonete_id=lanch.id,
        produto_id=produto.id, quantidade=10,
    ))
    part = ParticipacaoRodada(
        rodada_id=rodada.id, lanchonete_id=lanch.id,
        pedido_enviado_em=datetime.now(timezone.utc),
    )
    db.session.add(part)
    db.session.commit()
    return rodada.id, part.id


def test_pedido_aprovar_dispara_notif_lanchonete(app, client_admin):
    rodada_id, part_id = _seed_pedido_pendente()
    _vincula_chat_ids()
    os.environ["TELEGRAM_BOT_TOKEN"] = "x"
    try:
        with patch("app.services.notificacoes.requests.post") as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {"ok": True}
            token = _get_csrf(client_admin, f"/admin/rodadas/{rodada_id}/moderar-pedidos")
            client_admin.post(
                f"/admin/rodadas/{rodada_id}/moderar-pedidos",
                data={"csrf_token": token, "participacao_id": part_id, "acao": "aprovar"},
                follow_redirects=False,
            )
        assert mock_post.call_count == 1
        assert "Pedido aprovado" in mock_post.call_args.kwargs["json"]["text"]
    finally:
        os.environ.pop("TELEGRAM_BOT_TOKEN", None)


def test_pedido_aprovar_idempotente(app, client_admin):
    """2 cliques no aprovar nao duplicam notif (guarda ja existia)."""
    rodada_id, part_id = _seed_pedido_pendente()
    _vincula_chat_ids()
    os.environ["TELEGRAM_BOT_TOKEN"] = "x"
    try:
        with patch("app.services.notificacoes.requests.post") as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {"ok": True}
            token = _get_csrf(client_admin, f"/admin/rodadas/{rodada_id}/moderar-pedidos")
            client_admin.post(
                f"/admin/rodadas/{rodada_id}/moderar-pedidos",
                data={"csrf_token": token, "participacao_id": part_id, "acao": "aprovar"},
                follow_redirects=False,
            )
            client_admin.post(
                f"/admin/rodadas/{rodada_id}/moderar-pedidos",
                data={"csrf_token": token, "participacao_id": part_id, "acao": "aprovar"},
                follow_redirects=False,
            )
        assert mock_post.call_count == 1
    finally:
        os.environ.pop("TELEGRAM_BOT_TOKEN", None)


def test_pedido_devolver_idempotente_sem_reenvio(app, client_admin):
    """Devolver 2x sem reenvio da lanchonete: segundo retorna sem disparar
    notif. Guard nova: 'pedido_devolvido_em is not None and pedido_enviado_em
    is None'."""
    rodada_id, part_id = _seed_pedido_pendente()
    _vincula_chat_ids()
    os.environ["TELEGRAM_BOT_TOKEN"] = "x"
    try:
        with patch("app.services.notificacoes.requests.post") as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {"ok": True}
            token = _get_csrf(client_admin, f"/admin/rodadas/{rodada_id}/moderar-pedidos")
            client_admin.post(
                f"/admin/rodadas/{rodada_id}/moderar-pedidos",
                data={"csrf_token": token, "participacao_id": part_id,
                      "acao": "devolver", "motivo": "volume alto"},
                follow_redirects=False,
            )
            chamadas_1 = mock_post.call_count
            client_admin.post(
                f"/admin/rodadas/{rodada_id}/moderar-pedidos",
                data={"csrf_token": token, "participacao_id": part_id,
                      "acao": "devolver", "motivo": "outra vez"},
                follow_redirects=False,
            )
            chamadas_2 = mock_post.call_count
        assert chamadas_1 == 1
        assert chamadas_2 == 1  # NAO duplicou
    finally:
        os.environ.pop("TELEGRAM_BOT_TOKEN", None)


def test_pedido_reprovar_idempotente(app, client_admin):
    """Reprovar eh terminal — 2 cliques nao duplicam notif. Guard nova:
    'pedido_reprovado_em is not None'."""
    rodada_id, part_id = _seed_pedido_pendente()
    _vincula_chat_ids()
    os.environ["TELEGRAM_BOT_TOKEN"] = "x"
    try:
        with patch("app.services.notificacoes.requests.post") as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {"ok": True}
            token = _get_csrf(client_admin, f"/admin/rodadas/{rodada_id}/moderar-pedidos")
            client_admin.post(
                f"/admin/rodadas/{rodada_id}/moderar-pedidos",
                data={"csrf_token": token, "participacao_id": part_id, "acao": "reprovar"},
                follow_redirects=False,
            )
            client_admin.post(
                f"/admin/rodadas/{rodada_id}/moderar-pedidos",
                data={"csrf_token": token, "participacao_id": part_id, "acao": "reprovar"},
                follow_redirects=False,
            )
        assert mock_post.call_count == 1  # so 1 vez
    finally:
        os.environ.pop("TELEGRAM_BOT_TOKEN", None)


def test_pedido_reverter_sem_aprovacao_nao_muda_nada(app, client_admin):
    """Reverter sem aprovacao em vigor: retorna sem mutar. Guard nova:
    'pedido_aprovado_em is None'."""
    rodada_id, part_id = _seed_pedido_pendente()
    enviada_em_antes = db.session.get(ParticipacaoRodada, part_id).pedido_enviado_em
    os.environ["TELEGRAM_BOT_TOKEN"] = "x"
    try:
        with patch("app.services.notificacoes.requests.post") as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {"ok": True}
            token = _get_csrf(client_admin, f"/admin/rodadas/{rodada_id}/moderar-pedidos")
            client_admin.post(
                f"/admin/rodadas/{rodada_id}/moderar-pedidos",
                data={"csrf_token": token, "participacao_id": part_id, "acao": "reverter"},
                follow_redirects=False,
            )
        assert mock_post.call_count == 0
        # pedido_enviado_em nao mexido
        part = db.session.get(ParticipacaoRodada, part_id)
        assert part.pedido_aprovado_em is None
        assert part.pedido_enviado_em == enviada_em_antes
    finally:
        os.environ.pop("TELEGRAM_BOT_TOKEN", None)
