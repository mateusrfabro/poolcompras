"""Testes dos helpers de notificacao em massa (transicoes de status de rodada).

Cobre 5 helpers em app/services/notificacoes.py:
- notificar_fornecedores_nova_rodada
- notificar_lanchonetes_rodada_aberta
- notificar_fornecedores_cotacao_final
- notificar_lanchonetes_cotacao_aprovada
- notificar_cancelamento

Padrao: mock em requests.post pra nao bater na API real, set TELEGRAM_BOT_TOKEN
no env e set telegram_chat_id nos usuarios target. Cada helper retorna o numero
de notificacoes enviadas com sucesso — eh nessa metrica que cravamos as asserts.
"""
import os
from unittest.mock import patch, MagicMock

from app import db
from app.models import (
    Usuario, Lanchonete, Fornecedor, Rodada, RodadaProduto, Cotacao, ItemPedido,
)
from app.services.notificacoes import (
    notificar_fornecedores_nova_rodada,
    notificar_lanchonetes_rodada_aberta,
    notificar_fornecedores_cotacao_final,
    notificar_lanchonetes_cotacao_aprovada,
    notificar_cancelamento,
)


def _setar_chat_ids(emails):
    """Helper: marca chat_id em uma lista de emails de usuarios."""
    for i, email in enumerate(emails, start=1):
        u = Usuario.query.filter_by(email=email).first()
        u.telegram_chat_id = 1000 + i
    db.session.commit()


def _resp_ok():
    r = MagicMock()
    r.status_code = 200
    r.json.return_value = {"ok": True, "result": {}}
    return r


def _rodada():
    return Rodada.query.first()


def test_nova_rodada_so_fornecedores_ativos_com_chat_id(app):
    """notificar_fornecedores_nova_rodada: 1 fornecedor ativo com chat_id => 1 notif."""
    _setar_chat_ids(["forn@test.com"])
    os.environ["TELEGRAM_BOT_TOKEN"] = "x"
    try:
        with patch("app.services.notificacoes.requests.post", return_value=_resp_ok()) as mock_post:
            n = notificar_fornecedores_nova_rodada(_rodada())
        assert n == 1
        assert mock_post.call_count == 1
        # Mensagem inclui nome da rodada
        assert "Rodada Teste" in mock_post.call_args.kwargs["json"]["text"]
    finally:
        os.environ.pop("TELEGRAM_BOT_TOKEN", None)


def test_nova_rodada_ignora_fornecedor_inativo(app):
    """Fornecedor com ativo=False nao recebe notif."""
    f = Fornecedor.query.first()
    f.ativo = False
    db.session.commit()
    _setar_chat_ids(["forn@test.com"])
    os.environ["TELEGRAM_BOT_TOKEN"] = "x"
    try:
        with patch("app.services.notificacoes.requests.post", return_value=_resp_ok()):
            n = notificar_fornecedores_nova_rodada(_rodada())
        assert n == 0
    finally:
        os.environ.pop("TELEGRAM_BOT_TOKEN", None)


def test_rodada_aberta_so_lanchonetes_ativas(app):
    """2 lanchonetes ativas com chat_id => 2 notifs. Lanchonete inativa nao conta."""
    # Inativa a Lanch B
    lb = Lanchonete.query.filter_by(nome_fantasia="Lanch B").first()
    lb.ativa = False
    db.session.commit()
    _setar_chat_ids(["lancha@test.com", "lanchb@test.com"])
    os.environ["TELEGRAM_BOT_TOKEN"] = "x"
    try:
        with patch("app.services.notificacoes.requests.post", return_value=_resp_ok()) as mock_post:
            n = notificar_lanchonetes_rodada_aberta(_rodada())
        assert n == 1  # so a Lanch A (ativa)
        assert mock_post.call_count == 1
    finally:
        os.environ.pop("TELEGRAM_BOT_TOKEN", None)


def test_cotacao_final_so_fornecedores_que_cotaram_partida(app):
    """notificar_fornecedores_cotacao_final filtra por preco_partida is not None."""
    rodada = _rodada()
    fornecedor = Fornecedor.query.first()
    # Marca preco de partida no RodadaProduto
    rp = RodadaProduto.query.filter_by(rodada_id=rodada.id).first()
    rp.adicionado_por_fornecedor_id = fornecedor.id
    rp.preco_partida = 25.50
    db.session.commit()

    _setar_chat_ids(["forn@test.com"])
    os.environ["TELEGRAM_BOT_TOKEN"] = "x"
    try:
        with patch("app.services.notificacoes.requests.post", return_value=_resp_ok()) as mock_post:
            n = notificar_fornecedores_cotacao_final(rodada)
        assert n == 1
        # Mensagem fala em "preço final" e cita rodada
        txt = mock_post.call_args.kwargs["json"]["text"]
        assert "preço final" in txt or "preco final" in txt.lower()
    finally:
        os.environ.pop("TELEGRAM_BOT_TOKEN", None)


def test_cotacao_final_sem_preco_partida_nao_notifica(app):
    """Sem RodadaProduto com preco_partida, retorna 0."""
    _setar_chat_ids(["forn@test.com"])
    os.environ["TELEGRAM_BOT_TOKEN"] = "x"
    try:
        with patch("app.services.notificacoes.requests.post", return_value=_resp_ok()) as mock_post:
            n = notificar_fornecedores_cotacao_final(_rodada())
        assert n == 0
        assert mock_post.call_count == 0
    finally:
        os.environ.pop("TELEGRAM_BOT_TOKEN", None)


def test_cotacao_aprovada_so_lanchonetes_que_pediram(app):
    """notificar_lanchonetes_cotacao_aprovada: so quem fez ItemPedido na rodada."""
    rodada = _rodada()
    fornecedor = Fornecedor.query.first()
    lanch_a = Lanchonete.query.filter_by(nome_fantasia="Lanch A").first()
    produto_id = RodadaProduto.query.filter_by(rodada_id=rodada.id).first().produto_id

    # Lanch A pediu, Lanch B nao
    db.session.add(ItemPedido(
        rodada_id=rodada.id, lanchonete_id=lanch_a.id,
        produto_id=produto_id, quantidade=10,
    ))
    db.session.commit()

    _setar_chat_ids(["lancha@test.com", "lanchb@test.com"])
    os.environ["TELEGRAM_BOT_TOKEN"] = "x"
    try:
        with patch("app.services.notificacoes.requests.post", return_value=_resp_ok()) as mock_post:
            n = notificar_lanchonetes_cotacao_aprovada(rodada, fornecedor)
        assert n == 1  # so Lanch A
        assert mock_post.call_count == 1
        txt = mock_post.call_args.kwargs["json"]["text"]
        assert "Fornec Teste" in txt
    finally:
        os.environ.pop("TELEGRAM_BOT_TOKEN", None)


def test_cancelamento_notifica_lanchonetes_e_fornecedores_envolvidos(app):
    """notificar_cancelamento: quem pediu (ItemPedido) + quem cotou (Cotacao)."""
    rodada = _rodada()
    fornecedor = Fornecedor.query.first()
    lanch_a = Lanchonete.query.filter_by(nome_fantasia="Lanch A").first()
    produto_id = RodadaProduto.query.filter_by(rodada_id=rodada.id).first().produto_id

    db.session.add(ItemPedido(
        rodada_id=rodada.id, lanchonete_id=lanch_a.id,
        produto_id=produto_id, quantidade=10,
    ))
    db.session.add(Cotacao(
        rodada_id=rodada.id, fornecedor_id=fornecedor.id,
        produto_id=produto_id, preco_unitario=20.0,
    ))
    db.session.commit()

    _setar_chat_ids(["lancha@test.com", "forn@test.com"])
    os.environ["TELEGRAM_BOT_TOKEN"] = "x"
    try:
        with patch("app.services.notificacoes.requests.post", return_value=_resp_ok()) as mock_post:
            n = notificar_cancelamento(rodada)
        assert n == 2  # 1 lanchonete + 1 fornecedor
        assert mock_post.call_count == 2
    finally:
        os.environ.pop("TELEGRAM_BOT_TOKEN", None)


def test_cancelamento_sem_envolvidos_retorna_zero(app):
    """Rodada sem ItemPedido nem Cotacao => 0 notificacoes."""
    os.environ["TELEGRAM_BOT_TOKEN"] = "x"
    try:
        with patch("app.services.notificacoes.requests.post", return_value=_resp_ok()) as mock_post:
            n = notificar_cancelamento(_rodada())
        assert n == 0
        assert mock_post.call_count == 0
    finally:
        os.environ.pop("TELEGRAM_BOT_TOKEN", None)


def test_helpers_tolerantes_a_canal_inativo(app):
    """Sem TELEGRAM_BOT_TOKEN, helpers nao levantam — caem no fallback do log
    e retornam 0 (nada confirmado)."""
    _setar_chat_ids(["forn@test.com", "lancha@test.com"])
    os.environ.pop("TELEGRAM_BOT_TOKEN", None)
    # Cada helper deve ser idempotente e nao levantar mesmo sem token
    assert notificar_fornecedores_nova_rodada(_rodada()) == 0
    assert notificar_lanchonetes_rodada_aberta(_rodada()) == 0
