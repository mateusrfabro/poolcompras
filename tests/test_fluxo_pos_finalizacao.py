"""Bateria de testes do fluxo pos-finalizacao:

Ordem canonica:
  aceitar proposta -> comprovante -> (fornecedor) confirmar pagto ->
  (fornecedor) informar entrega -> confirmar recebimento -> avaliar

Cobre happy path e IDOR por rota.
"""
import io
import re
from datetime import datetime, timezone

from app import db
from app.models import (
    Rodada, Produto, Lanchonete, Fornecedor, ItemPedido, Cotacao, RodadaProduto,
    ParticipacaoRodada, AvaliacaoRodada, EventoRodada,
)


# PNG mimimo valido (1x1 pixel). Precisa passar no check de MAGIC_BYTES.
PNG_1X1 = bytes([
    0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A,  # signature
    0x00, 0x00, 0x00, 0x0D, 0x49, 0x48, 0x44, 0x52,  # IHDR chunk
    0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01,
    0x08, 0x06, 0x00, 0x00, 0x00, 0x1F, 0x15, 0xC4, 0x89,
    0x00, 0x00, 0x00, 0x0D, 0x49, 0x44, 0x41, 0x54,  # IDAT
    0x78, 0x9C, 0x62, 0x00, 0x01, 0x00, 0x00, 0x05,
    0x00, 0x01, 0x0D, 0x0A, 0x2D, 0xB4,
    0x00, 0x00, 0x00, 0x00, 0x49, 0x45, 0x4E, 0x44,  # IEND
    0xAE, 0x42, 0x60, 0x82,
])


def _get_csrf(client, url):
    r = client.get(url)
    m = re.search(rb'name="csrf_token"[^>]*value="([^"]+)"', r.data)
    return m.group(1).decode() if m else None


def _troca_para(client, email, senha="testpass"):
    """Faz logout do client atual e entra com outro usuario.

    Evita o quirk onde 2 test_clients no mesmo app_context compartilham
    session e o segundo login nao tem efeito (visto antes no IDOR).
    Logout virou POST (defesa contra logout-CSRF). CSRF desabilitado em testes.
    """
    client.post("/logout", follow_redirects=False)
    client.post("/login", data={"email": email, "senha": senha},
                follow_redirects=False)


def _prepara_rodada_finalizada():
    """Rodada finalizada com cotacao selecionada pra lanchA + forn."""
    rodada = Rodada.query.first()
    produto = Produto.query.first()
    lanchA = Lanchonete.query.filter_by(nome_fantasia="Lanch A").first()
    forn = Fornecedor.query.first()

    rp = RodadaProduto.query.filter_by(rodada_id=rodada.id, produto_id=produto.id).first()
    rp.preco_partida = 20.00

    db.session.add(Cotacao(
        rodada_id=rodada.id, fornecedor_id=forn.id,
        produto_id=produto.id, preco_unitario=15.00, selecionada=True,
    ))
    db.session.add(ItemPedido(
        rodada_id=rodada.id, lanchonete_id=lanchA.id,
        produto_id=produto.id, quantidade=10,
    ))
    rodada.status = "finalizada"
    db.session.commit()
    return rodada.id, lanchA.id, forn.id


# ---------- aceitar / recusar ----------

def test_lanchonete_aceita_proposta(app, client_lanchA):
    rodada_id, lanch_id, _ = _prepara_rodada_finalizada()

    csrf = _get_csrf(client_lanchA, f"/minhas-rodadas/{rodada_id}")
    client_lanchA.post(f"/fluxo/rodada/{rodada_id}/aceitar",
                       data={"csrf_token": csrf}, follow_redirects=False)

    p = ParticipacaoRodada.query.filter_by(
        rodada_id=rodada_id, lanchonete_id=lanch_id,
    ).first()
    assert p is not None
    assert p.aceite_proposta is True
    assert p.aceite_em is not None
    # Evento registrado
    evt = EventoRodada.query.filter_by(
        rodada_id=rodada_id, tipo=EventoRodada.TIPO_PROPOSTA_ACEITA,
    ).first()
    assert evt is not None


def test_lanchonete_recusa_proposta(app, client_lanchA):
    rodada_id, lanch_id, _ = _prepara_rodada_finalizada()
    csrf = _get_csrf(client_lanchA, f"/minhas-rodadas/{rodada_id}")
    client_lanchA.post(f"/fluxo/rodada/{rodada_id}/recusar",
                       data={"csrf_token": csrf}, follow_redirects=False)
    p = ParticipacaoRodada.query.filter_by(
        rodada_id=rodada_id, lanchonete_id=lanch_id,
    ).first()
    assert p.aceite_proposta is False


def test_fornecedor_nao_aceita_proposta(app, client_forn):
    """@lanchonete_required redireciona non-lanchonete com 302 (flash + dashboard)."""
    rodada_id, _, _ = _prepara_rodada_finalizada()
    r = client_forn.post(f"/fluxo/rodada/{rodada_id}/aceitar", follow_redirects=False)
    assert r.status_code == 302  # decorator redireciona pro dashboard


def test_lanchonete_B_nao_afeta_participacao_de_A(app, client_lanchB):
    """Lanchonete B faz aceite — afeta apenas a propria participacao, nunca a de A."""
    rodada_id, lanchA_id, _ = _prepara_rodada_finalizada()
    lanchB_id = Lanchonete.query.filter_by(nome_fantasia="Lanch B").first().id

    csrf = _get_csrf(client_lanchB, f"/minhas-rodadas/{rodada_id}")
    client_lanchB.post(f"/fluxo/rodada/{rodada_id}/aceitar",
                       data={"csrf_token": csrf}, follow_redirects=False)

    # Participacao de B criada
    pB = ParticipacaoRodada.query.filter_by(
        rodada_id=rodada_id, lanchonete_id=lanchB_id,
    ).first()
    assert pB.aceite_proposta is True
    # Participacao de A NAO existe (ela nao fez aceite)
    pA = ParticipacaoRodada.query.filter_by(
        rodada_id=rodada_id, lanchonete_id=lanchA_id,
    ).first()
    assert pA is None


# ---------- comprovante ----------

def test_lanchonete_envia_comprovante(app, client_lanchA):
    rodada_id, lanch_id, _ = _prepara_rodada_finalizada()
    # Pre-aceita (comprovante exige aceite)
    csrf = _get_csrf(client_lanchA, f"/minhas-rodadas/{rodada_id}")
    client_lanchA.post(f"/fluxo/rodada/{rodada_id}/aceitar",
                       data={"csrf_token": csrf}, follow_redirects=False)

    csrf = _get_csrf(client_lanchA, f"/minhas-rodadas/{rodada_id}")
    data = {
        "csrf_token": csrf,
        "comprovante": (io.BytesIO(PNG_1X1), "pix.png"),
    }
    client_lanchA.post(f"/fluxo/rodada/{rodada_id}/comprovante",
                       data=data, content_type="multipart/form-data",
                       follow_redirects=False)

    p = ParticipacaoRodada.query.filter_by(
        rodada_id=rodada_id, lanchonete_id=lanch_id,
    ).first()
    assert p.comprovante_key is not None
    assert p.comprovante_em is not None


def test_comprovante_sem_aceite_eh_bloqueado(app, client_lanchA):
    rodada_id, lanch_id, _ = _prepara_rodada_finalizada()
    csrf = _get_csrf(client_lanchA, f"/minhas-rodadas/{rodada_id}")
    r = client_lanchA.post(
        f"/fluxo/rodada/{rodada_id}/comprovante",
        data={"csrf_token": csrf,
              "comprovante": (io.BytesIO(PNG_1X1), "pix.png")},
        content_type="multipart/form-data",
        follow_redirects=False,
    )
    # Redirect com flash de erro (estado nao muda)
    assert r.status_code == 302
    p = ParticipacaoRodada.query.filter_by(
        rodada_id=rodada_id, lanchonete_id=lanch_id,
    ).first()
    assert p is None or p.comprovante_key is None


def test_comprovante_arquivo_invalido_rejeita(app, client_lanchA):
    """Arquivo com extensao PNG mas conteudo de texto — nao passa magic bytes."""
    rodada_id, lanch_id, _ = _prepara_rodada_finalizada()
    csrf = _get_csrf(client_lanchA, f"/minhas-rodadas/{rodada_id}")
    client_lanchA.post(f"/fluxo/rodada/{rodada_id}/aceitar",
                       data={"csrf_token": csrf}, follow_redirects=False)

    csrf = _get_csrf(client_lanchA, f"/minhas-rodadas/{rodada_id}")
    client_lanchA.post(
        f"/fluxo/rodada/{rodada_id}/comprovante",
        data={"csrf_token": csrf,
              "comprovante": (io.BytesIO(b"texto-puro-sem-png"), "fake.png")},
        content_type="multipart/form-data",
        follow_redirects=False,
    )
    p = ParticipacaoRodada.query.filter_by(
        rodada_id=rodada_id, lanchonete_id=lanch_id,
    ).first()
    assert p.comprovante_key is None


# ---------- fornecedor: confirma pagamento + informa entrega ----------

def _prepara_ate_comprovante(app, client_lanchA):
    """Retorna (rodada_id, lanch_id, forn_id) com comprovante ja enviado."""
    rodada_id, lanch_id, forn_id = _prepara_rodada_finalizada()
    csrf = _get_csrf(client_lanchA, f"/minhas-rodadas/{rodada_id}")
    client_lanchA.post(f"/fluxo/rodada/{rodada_id}/aceitar",
                       data={"csrf_token": csrf}, follow_redirects=False)
    csrf = _get_csrf(client_lanchA, f"/minhas-rodadas/{rodada_id}")
    client_lanchA.post(
        f"/fluxo/rodada/{rodada_id}/comprovante",
        data={"csrf_token": csrf,
              "comprovante": (io.BytesIO(PNG_1X1), "pix.png")},
        content_type="multipart/form-data",
        follow_redirects=False,
    )
    return rodada_id, lanch_id, forn_id


def test_fornecedor_confirma_pagamento(app, client_lanchA):
    rodada_id, lanch_id, forn_id = _prepara_ate_comprovante(app, client_lanchA)
    # Troca o mesmo client pro fornecedor (contorna quirk de 2 clients)
    _troca_para(client_lanchA, "forn@test.com")
    csrf = _get_csrf(client_lanchA, "/fornecedor/dashboard")
    client_lanchA.post(
        f"/fluxo/rodada/{rodada_id}/lanchonete/{lanch_id}/pagamento",
        data={"csrf_token": csrf}, follow_redirects=False,
    )
    p = ParticipacaoRodada.query.filter_by(
        rodada_id=rodada_id, lanchonete_id=lanch_id,
    ).first()
    assert p.pagamento_confirmado_em is not None


def test_lanchonete_nao_confirma_proprio_pagamento(app, client_lanchA):
    """Acao eh exclusiva do fornecedor. _so_fornecedor_da_rodada retorna 403."""
    rodada_id, lanch_id, _ = _prepara_ate_comprovante(app, client_lanchA)
    csrf = _get_csrf(client_lanchA, f"/minhas-rodadas/{rodada_id}")
    r = client_lanchA.post(
        f"/fluxo/rodada/{rodada_id}/lanchonete/{lanch_id}/pagamento",
        data={"csrf_token": csrf}, follow_redirects=False,
    )
    assert r.status_code == 403


def test_fornecedor_informa_entrega_apos_pagamento(app, client_lanchA):
    rodada_id, lanch_id, _ = _prepara_ate_comprovante(app, client_lanchA)
    _troca_para(client_lanchA, "forn@test.com")
    csrf = _get_csrf(client_lanchA, "/fornecedor/dashboard")
    client_lanchA.post(
        f"/fluxo/rodada/{rodada_id}/lanchonete/{lanch_id}/pagamento",
        data={"csrf_token": csrf}, follow_redirects=False,
    )
    csrf = _get_csrf(client_lanchA, "/fornecedor/dashboard")
    client_lanchA.post(
        f"/fluxo/rodada/{rodada_id}/lanchonete/{lanch_id}/entrega",
        data={"csrf_token": csrf, "entrega_data": "2026-05-01"},
        follow_redirects=False,
    )
    p = ParticipacaoRodada.query.filter_by(
        rodada_id=rodada_id, lanchonete_id=lanch_id,
    ).first()
    assert p.entrega_informada_em is not None
    assert p.entrega_data.isoformat() == "2026-05-01"


def test_entrega_sem_pagamento_confirmado_bloqueia(app, client_lanchA):
    rodada_id, lanch_id, _ = _prepara_ate_comprovante(app, client_lanchA)
    _troca_para(client_lanchA, "forn@test.com")
    csrf = _get_csrf(client_lanchA, "/fornecedor/dashboard")
    client_lanchA.post(
        f"/fluxo/rodada/{rodada_id}/lanchonete/{lanch_id}/entrega",
        data={"csrf_token": csrf, "entrega_data": "2026-05-01"},
        follow_redirects=False,
    )
    p = ParticipacaoRodada.query.filter_by(
        rodada_id=rodada_id, lanchonete_id=lanch_id,
    ).first()
    assert p.entrega_informada_em is None


# ---------- recebimento + avaliacao ----------

def _prepara_ate_entrega(app, client):
    """Prepara ate 'entrega informada' usando o MESMO client (troca usuario no meio)."""
    rodada_id, lanch_id, forn_id = _prepara_ate_comprovante(app, client)
    _troca_para(client, "forn@test.com")
    csrf = _get_csrf(client, "/fornecedor/dashboard")
    client.post(f"/fluxo/rodada/{rodada_id}/lanchonete/{lanch_id}/pagamento",
                data={"csrf_token": csrf}, follow_redirects=False)
    csrf = _get_csrf(client, "/fornecedor/dashboard")
    client.post(f"/fluxo/rodada/{rodada_id}/lanchonete/{lanch_id}/entrega",
                data={"csrf_token": csrf, "entrega_data": "2026-05-01"},
                follow_redirects=False)
    # Volta pra lanchonete pra proximas acoes
    _troca_para(client, "lancha@test.com")
    return rodada_id, lanch_id, forn_id


def test_lanchonete_confirma_recebimento_ok(app, client_lanchA):
    rodada_id, lanch_id, _ = _prepara_ate_entrega(app, client_lanchA)
    csrf = _get_csrf(client_lanchA, f"/minhas-rodadas/{rodada_id}")
    client_lanchA.post(
        f"/fluxo/rodada/{rodada_id}/confirmar-recebimento",
        data={"csrf_token": csrf, "status": "ok"},
        follow_redirects=False,
    )
    p = ParticipacaoRodada.query.filter_by(
        rodada_id=rodada_id, lanchonete_id=lanch_id,
    ).first()
    assert p.recebimento_ok is True
    assert p.recebimento_em is not None


def test_lanchonete_reporta_problema_no_recebimento(app, client_lanchA):
    rodada_id, lanch_id, _ = _prepara_ate_entrega(app, client_lanchA)
    csrf = _get_csrf(client_lanchA, f"/minhas-rodadas/{rodada_id}")
    client_lanchA.post(
        f"/fluxo/rodada/{rodada_id}/confirmar-recebimento",
        data={"csrf_token": csrf, "status": "problema",
              "observacao": "Chegou faltando 2 pacotes"},
        follow_redirects=False,
    )
    p = ParticipacaoRodada.query.filter_by(
        rodada_id=rodada_id, lanchonete_id=lanch_id,
    ).first()
    assert p.recebimento_ok is False
    assert "faltando" in (p.recebimento_observacao or "")


def test_avaliacao_alta_replica_pra_todos_fornecedores(app, client_lanchA):
    rodada_id, lanch_id, forn_id = _prepara_ate_entrega(app, client_lanchA)
    csrf = _get_csrf(client_lanchA, f"/minhas-rodadas/{rodada_id}")
    client_lanchA.post(f"/fluxo/rodada/{rodada_id}/confirmar-recebimento",
                       data={"csrf_token": csrf, "status": "ok"},
                       follow_redirects=False)
    csrf = _get_csrf(client_lanchA, f"/minhas-rodadas/{rodada_id}")
    client_lanchA.post(f"/fluxo/rodada/{rodada_id}/avaliar",
                       data={"csrf_token": csrf, "estrelas": "5"},
                       follow_redirects=False)

    p = ParticipacaoRodada.query.filter_by(
        rodada_id=rodada_id, lanchonete_id=lanch_id,
    ).first()
    assert p.avaliacao_geral == 5
    av = AvaliacaoRodada.query.filter_by(
        rodada_id=rodada_id, lanchonete_id=lanch_id, fornecedor_id=forn_id,
    ).first()
    assert av is not None
    assert av.estrelas == 5


def test_avaliacao_baixa_redireciona_pra_detalhada(app, client_lanchA):
    rodada_id, lanch_id, _ = _prepara_ate_entrega(app, client_lanchA)
    csrf = _get_csrf(client_lanchA, f"/minhas-rodadas/{rodada_id}")
    client_lanchA.post(f"/fluxo/rodada/{rodada_id}/confirmar-recebimento",
                       data={"csrf_token": csrf, "status": "ok"},
                       follow_redirects=False)
    csrf = _get_csrf(client_lanchA, f"/minhas-rodadas/{rodada_id}")
    r = client_lanchA.post(f"/fluxo/rodada/{rodada_id}/avaliar",
                           data={"csrf_token": csrf, "estrelas": "2"},
                           follow_redirects=False)
    assert r.status_code == 302
    assert "/avaliar-detalhado" in r.headers["Location"]
    p = ParticipacaoRodada.query.filter_by(
        rodada_id=rodada_id, lanchonete_id=lanch_id,
    ).first()
    assert p.avaliacao_geral == 2


def test_avaliacao_sem_confirmar_recebimento_bloqueia(app, client_lanchA):
    rodada_id, lanch_id, _ = _prepara_ate_entrega(app, client_lanchA)
    csrf = _get_csrf(client_lanchA, f"/minhas-rodadas/{rodada_id}")
    client_lanchA.post(f"/fluxo/rodada/{rodada_id}/avaliar",
                       data={"csrf_token": csrf, "estrelas": "5"},
                       follow_redirects=False)
    p = ParticipacaoRodada.query.filter_by(
        rodada_id=rodada_id, lanchonete_id=lanch_id,
    ).first()
    assert p.avaliacao_geral is None
