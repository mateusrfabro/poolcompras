"""Kanban de rodadas + drill-down 'situacao'."""
from datetime import datetime, timezone, timedelta

from app import db
from app.models import (
    Rodada, ParticipacaoRodada, Lanchonete, Cotacao, Fornecedor, Produto,
)


def test_kanban_rodadas_admin_renderiza(client_admin):
    r = client_admin.get("/admin/rodadas/kanban")
    assert r.status_code == 200
    body = r.data.decode("utf-8", errors="ignore")
    assert "Operação" in body
    # Todas 6 colunas presentes
    assert "Preparando" in body
    assert "Aguardando cotação" in body
    assert "Aberta" in body
    assert "negociação" in body
    assert "Finalizada" in body
    assert "Cancelada" in body


def test_rodada_seed_aparece_na_coluna_aberta(client_admin):
    """Conftest cria 1 Rodada Teste com status='aberta'."""
    r = client_admin.get("/admin/rodadas/kanban")
    assert b"Rodada Teste" in r.data


def test_kanban_nao_quebra_com_multiplos_status(client_admin, app):
    """Cria rodadas em varios status — kanban renderiza todas sem 500."""
    agora = datetime.now(timezone.utc)
    for status in ("preparando", "aguardando_cotacao", "em_negociacao",
                   "finalizada", "cancelada"):
        db.session.add(Rodada(
            nome=f"Rodada {status}",
            data_abertura=agora,
            data_fechamento=agora + timedelta(hours=2),
            status=status,
        ))
    db.session.commit()

    r = client_admin.get("/admin/rodadas/kanban")
    assert r.status_code == 200
    for status in ("preparando", "aguardando_cotacao",
                   "em_negociacao", "finalizada", "cancelada"):
        assert f"Rodada {status}".encode() in r.data


def test_situacao_rodada_drilldown_renderiza(client_admin, app):
    """Drill-down de uma rodada com participantes mostra etapa."""
    rodada = Rodada.query.first()
    lanch = Lanchonete.query.first()
    db.session.add(ParticipacaoRodada(
        rodada_id=rodada.id,
        lanchonete_id=lanch.id,
        pedido_enviado_em=datetime.now(timezone.utc),
    ))
    db.session.commit()

    r = client_admin.get(f"/admin/rodadas/{rodada.id}/situacao")
    assert r.status_code == 200
    assert lanch.nome_fantasia.encode() in r.data
    body = r.data.decode("utf-8", errors="ignore")
    assert "pedido enviado" in body  # etapa atual


def test_situacao_rodada_404_inexistente(client_admin):
    r = client_admin.get("/admin/rodadas/999999/situacao")
    assert r.status_code == 404


def test_kanban_rodadas_lanchonete_negada(client_lanchA):
    r = client_lanchA.get("/admin/rodadas/kanban")
    assert r.status_code in (302, 403)


def test_kanban_rodadas_fornecedor_negado(client_forn):
    r = client_forn.get("/admin/rodadas/kanban")
    assert r.status_code in (302, 403)


def test_situacao_mostra_fornecedores_que_cotaram(client_admin, app):
    rodada = Rodada.query.first()
    forn = Fornecedor.query.first()
    produto = Produto.query.first()
    db.session.add(Cotacao(
        rodada_id=rodada.id,
        fornecedor_id=forn.id,
        produto_id=produto.id,
        preco_unitario=10.50,
        selecionada=True,
    ))
    db.session.commit()

    r = client_admin.get(f"/admin/rodadas/{rodada.id}/situacao")
    assert r.status_code == 200
    assert forn.razao_social.encode() in r.data


def test_etapa_progressao_correta(client_admin, app):
    """Lanchonete ja avaliou — etapa final 'avaliou' aparece."""
    rodada = Rodada.query.first()
    lanch = Lanchonete.query.first()
    agora = datetime.now(timezone.utc)
    db.session.add(ParticipacaoRodada(
        rodada_id=rodada.id,
        lanchonete_id=lanch.id,
        pedido_enviado_em=agora,
        pedido_aprovado_em=agora,
        aceite_proposta=True,
        aceite_em=agora,
        comprovante_em=agora,
        pagamento_confirmado_em=agora,
        entrega_informada_em=agora,
        recebimento_ok=True,
        recebimento_em=agora,
        avaliacao_geral=5,
        avaliacao_em=agora,
    ))
    db.session.commit()

    r = client_admin.get(f"/admin/rodadas/{rodada.id}/situacao")
    body = r.data.decode("utf-8", errors="ignore")
    assert "avaliou" in body
