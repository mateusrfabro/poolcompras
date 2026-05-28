"""Testes de aceite parcial (decisao Mateus mai/2026 — opcao MINI).

Lanchonete pode aceitar a proposta consolidada da rodada e RECUSAR
fornecedor especifico via lista de IDs em fornecedor_recusado[].

Fluxo: form POST /fluxo/rodada/X/aceitar com:
- fornecedor_recusado (multi) = [fornecedor_id, ...]

Ausencia da lista = aceite total (compat retroativa).
"""
from datetime import datetime, timezone

from werkzeug.security import generate_password_hash

from app import db
from app.models import (
    Cotacao, Fornecedor, ItemPedido, Lanchonete, ParticipacaoRodada,
    Produto, RecusaFornecedor, Rodada, RodadaProduto, SubmissaoCotacao, Usuario,
)
from app.services.aceite_parcial import (
    fornecedor_recusado, fornecedores_recusados_por_lanchonete,
    registrar_recusas,
)
from app.services.vendas_efetivadas import linhas_efetivadas


def _agora():
    return datetime.now(timezone.utc)


def _csrf(client, url):
    """Extrai csrf_token de uma rota GET (token global serve pra qualquer POST)."""
    r = client.get(url)
    import re
    m = re.search(rb'name="csrf_token" value="([^"]+)"', r.data)
    return m.group(1).decode() if m else ""


def _cenario_2_fornecedores_aprovados():
    """Lanch A pedindo de 2 fornecedores (A vence Blend, B vence Brioche).
    Rodada finalizada — aceite disponivel."""
    rodada = Rodada.query.first()
    rodada.status = Rodada.STATUS_FINALIZADA
    lanchA = Lanchonete.query.filter_by(nome_fantasia="Lanch A").first()
    produto = Produto.query.first()

    # Forn A (do seed) — vence Blend
    fA = Fornecedor.query.first()

    # Cria Forn B + produto adicional
    uB = Usuario(email="fornb@test.com",
                 senha_hash=generate_password_hash("testpass"),
                 nome_responsavel="B", telefone="", tipo="fornecedor")
    db.session.add(uB); db.session.flush()
    fB = Fornecedor(usuario_id=uB.id, razao_social="Fornec B")
    db.session.add(fB); db.session.flush()

    p2 = Produto(nome="Brioche", categoria="Pao", subcategoria="Pao", unidade="unidade")
    db.session.add(p2); db.session.flush()

    # Submissoes aprovadas dos 2 fornecedores
    db.session.add(SubmissaoCotacao(rodada_id=rodada.id, fornecedor_id=fA.id,
                                     enviada_em=_agora(), aprovada_em=_agora()))
    db.session.add(SubmissaoCotacao(rodada_id=rodada.id, fornecedor_id=fB.id,
                                     enviada_em=_agora(), aprovada_em=_agora()))

    # A vence Blend (R$ 10), B vence Brioche (R$ 2)
    db.session.add(Cotacao(rodada_id=rodada.id, fornecedor_id=fA.id,
                            produto_id=produto.id, preco_unitario=10.00,
                            selecionada=True))
    db.session.add(Cotacao(rodada_id=rodada.id, fornecedor_id=fB.id,
                            produto_id=p2.id, preco_unitario=2.00,
                            selecionada=True))

    # Pedido da Lanch A: 5kg de Blend (A) + 100un de Brioche (B)
    db.session.add(ItemPedido(rodada_id=rodada.id, lanchonete_id=lanchA.id,
                               produto_id=produto.id, quantidade=5))
    db.session.add(ItemPedido(rodada_id=rodada.id, lanchonete_id=lanchA.id,
                               produto_id=p2.id, quantidade=100))

    # Participacao com pedido aprovado
    db.session.add(ParticipacaoRodada(
        rodada_id=rodada.id, lanchonete_id=lanchA.id,
        pedido_enviado_em=_agora(),
        pedido_aprovado_em=_agora(),
    ))

    # RodadaProduto pra cada
    if not RodadaProduto.query.filter_by(rodada_id=rodada.id, produto_id=produto.id).first():
        db.session.add(RodadaProduto(rodada_id=rodada.id, produto_id=produto.id,
                                       preco_partida=12.00))
    db.session.add(RodadaProduto(rodada_id=rodada.id, produto_id=p2.id,
                                   preco_partida=2.50))

    db.session.commit()
    return rodada.id, lanchA.id, fA.id, fB.id


# ============================================================================
# Helpers do service
# ============================================================================


def test_registrar_recusas_idempotente(app):
    """registrar_recusas pula linha ja existente."""
    rodada_id, lanchA_id, fA_id, fB_id = _cenario_2_fornecedores_aprovados()

    novos = registrar_recusas(rodada_id, lanchA_id, [fA_id])
    db.session.commit()
    assert novos == 1
    assert fornecedor_recusado(rodada_id, lanchA_id, fA_id) is True

    # Segunda chamada com mesmo ID: nao adiciona
    novos2 = registrar_recusas(rodada_id, lanchA_id, [fA_id, fB_id])
    db.session.commit()
    assert novos2 == 1  # so o B foi novo
    assert fornecedores_recusados_por_lanchonete(rodada_id, lanchA_id) == {fA_id, fB_id}


# ============================================================================
# Route aceitar_proposta
# ============================================================================


def test_aceitar_proposta_sem_recusa_compat_retroativa(app, client_lanchA):
    """Aceite SEM checkbox marcado funciona como antes (aceita tudo)."""
    rodada_id, lanchA_id, _, _ = _cenario_2_fornecedores_aprovados()

    csrf = _csrf(client_lanchA, f"/minhas-rodadas/{rodada_id}")
    r = client_lanchA.post(f"/fluxo/rodada/{rodada_id}/aceitar",
                           data={"csrf_token": csrf})
    assert r.status_code == 302

    p = ParticipacaoRodada.query.filter_by(
        rodada_id=rodada_id, lanchonete_id=lanchA_id,
    ).first()
    assert p.aceite_proposta is True
    assert fornecedores_recusados_por_lanchonete(rodada_id, lanchA_id) == set()


def test_aceitar_proposta_recusando_um_fornecedor(app, client_lanchA):
    """Aceite parcial: marca recusa de Forn B. Forn A continua aceito."""
    rodada_id, lanchA_id, fA_id, fB_id = _cenario_2_fornecedores_aprovados()

    csrf = _csrf(client_lanchA, f"/minhas-rodadas/{rodada_id}")
    r = client_lanchA.post(
        f"/fluxo/rodada/{rodada_id}/aceitar",
        data={"csrf_token": csrf, "fornecedor_recusado": str(fB_id)},
    )
    assert r.status_code == 302

    p = ParticipacaoRodada.query.filter_by(
        rodada_id=rodada_id, lanchonete_id=lanchA_id,
    ).first()
    assert p.aceite_proposta is True
    assert fornecedor_recusado(rodada_id, lanchA_id, fA_id) is False
    assert fornecedor_recusado(rodada_id, lanchA_id, fB_id) is True


def test_aceitar_ja_aceito_idempotente(app, client_lanchA):
    """Reaceite com nova lista de recusados nao re-grava (aceite_proposta=True ja)."""
    rodada_id, lanchA_id, fA_id, fB_id = _cenario_2_fornecedores_aprovados()

    csrf = _csrf(client_lanchA, f"/minhas-rodadas/{rodada_id}")
    # Primeiro aceite — recusa B
    client_lanchA.post(f"/fluxo/rodada/{rodada_id}/aceitar",
                       data={"csrf_token": csrf, "fornecedor_recusado": str(fB_id)})

    # Segundo aceite — tenta recusar A tambem
    client_lanchA.post(f"/fluxo/rodada/{rodada_id}/aceitar",
                       data={"csrf_token": csrf, "fornecedor_recusado": str(fA_id)})

    # So a primeira recusa vale (segunda foi bloqueada por aceite ja registrado)
    assert fornecedor_recusado(rodada_id, lanchA_id, fB_id) is True
    assert fornecedor_recusado(rodada_id, lanchA_id, fA_id) is False


# ============================================================================
# vendas_efetivadas (CMV / P&L) filtram recusados
# ============================================================================


def test_vendas_efetivadas_exclui_recusados(app):
    """Apos aceite parcial, vendas do fornecedor recusado nao aparecem em
    linhas_efetivadas (fonte unica do CMV e P&L)."""
    rodada_id, lanchA_id, fA_id, fB_id = _cenario_2_fornecedores_aprovados()

    # Antes do aceite, ainda nao conta nada (aceite_proposta is None)
    assert linhas_efetivadas(lanchonete_id=lanchA_id) == []

    # Lanchonete aceita TUDO
    p = ParticipacaoRodada.query.filter_by(
        rodada_id=rodada_id, lanchonete_id=lanchA_id,
    ).first()
    p.aceite_proposta = True
    p.aceite_em = _agora()
    db.session.commit()

    linhas = linhas_efetivadas(lanchonete_id=lanchA_id)
    assert len(linhas) == 2  # Blend (A) + Brioche (B)

    # Agora recusa Forn B retroativamente
    registrar_recusas(rodada_id, lanchA_id, [fB_id])
    db.session.commit()

    linhas = linhas_efetivadas(lanchonete_id=lanchA_id)
    assert len(linhas) == 1
    assert linhas[0].fornecedor_id == fA_id  # so Forn A sobrou


def test_vendas_efetivadas_pnl_fornecedor_recusado_zero(app):
    """P&L do fornecedor recusado fica vazio pra essa lanchonete."""
    rodada_id, lanchA_id, fA_id, fB_id = _cenario_2_fornecedores_aprovados()

    p = ParticipacaoRodada.query.filter_by(
        rodada_id=rodada_id, lanchonete_id=lanchA_id,
    ).first()
    p.aceite_proposta = True
    p.aceite_em = _agora()
    db.session.commit()

    # Forn B vendia 100un * R$ 2,00 = R$ 200 antes da recusa
    linhas_B = linhas_efetivadas(fornecedor_id=fB_id)
    assert len(linhas_B) == 1

    # Lanch A recusa Forn B
    registrar_recusas(rodada_id, lanchA_id, [fB_id])
    db.session.commit()

    linhas_B = linhas_efetivadas(fornecedor_id=fB_id)
    assert linhas_B == []


# ============================================================================
# Fluxo fornecedor (confirmar_pagamento / informar_entrega bloqueados)
# ============================================================================


def test_fornecedor_recusado_nao_confirma_pagamento(app):
    """Forn B foi recusado por Lanch A — endpoint confirmar_pagamento bloqueia."""
    rodada_id, lanchA_id, fA_id, fB_id = _cenario_2_fornecedores_aprovados()

    p = ParticipacaoRodada.query.filter_by(
        rodada_id=rodada_id, lanchonete_id=lanchA_id,
    ).first()
    p.aceite_proposta = True
    p.aceite_em = _agora()
    p.comprovante_key = "fake-key"
    p.comprovante_em = _agora()
    db.session.commit()

    registrar_recusas(rodada_id, lanchA_id, [fB_id])
    db.session.commit()

    # Forn B tenta confirmar pagamento da Lanch A
    c = app.test_client()
    r = c.post("/login", data={"email": "fornb@test.com", "senha": "testpass"},
               follow_redirects=False)
    assert r.status_code == 302

    csrf = _csrf(c, "/fornecedor")
    r = c.post(
        f"/fluxo/rodada/{rodada_id}/lanchonete/{lanchA_id}/pagamento",
        data={"csrf_token": csrf},
        follow_redirects=False,
    )
    # Redireciona com flash de erro — pagamento NAO confirmado
    assert r.status_code == 302
    p_after = db.session.get(ParticipacaoRodada, p.id)
    assert p_after.pagamento_confirmado_em is None


# ============================================================================
# Tela /historico/<id> mostra UI correta
# ============================================================================


def test_template_pre_aceite_lista_fornecedores(app, client_lanchA):
    """Pre-aceite: tela mostra 1 bloco por fornecedor com checkbox de recusar."""
    rodada_id, _, fA_id, fB_id = _cenario_2_fornecedores_aprovados()

    r = client_lanchA.get(f"/minhas-rodadas/{rodada_id}")
    assert r.status_code == 200
    # Botao "Aceitar tudo" foi substituido por "Confirmar aceite"
    assert "Confirmar aceite".encode("utf-8") in r.data
    # Checkbox de recusa por fornecedor
    assert b'name="fornecedor_recusado"' in r.data
    # Botao "Recusar tudo" continua disponivel (recusa total)
    assert "Recusar tudo".encode("utf-8") in r.data


def test_template_pos_aceite_parcial_lista_recusados(app, client_lanchA):
    """Pos-aceite parcial: tela mostra alert com lanchonetes recusadas."""
    rodada_id, lanchA_id, _, fB_id = _cenario_2_fornecedores_aprovados()

    # Lanch A aceita parcial, recusando Forn B
    csrf = _csrf(client_lanchA, f"/minhas-rodadas/{rodada_id}")
    client_lanchA.post(
        f"/fluxo/rodada/{rodada_id}/aceitar",
        data={"csrf_token": csrf, "fornecedor_recusado": str(fB_id)},
    )

    r = client_lanchA.get(f"/minhas-rodadas/{rodada_id}")
    assert r.status_code == 200
    # Alert mostrando recusados
    assert b"Fornec B" in r.data
    assert b"recusou" in r.data or b"Recusou" in r.data or b"recuso" in r.data
