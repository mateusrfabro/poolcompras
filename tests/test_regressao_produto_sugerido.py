"""Testes de regressao pros bugs corrigidos no ciclo de auditoria:

1. Admin recusando sugestao de produto NAO deve deletar/desativar
   o Produto globalmente (antes: rp.produto.ativo=False).
2. Produto sugerido nasce ativo=False pra nao poluir catalogo global
   ate admin aprovar; aprovacao ativa o produto.
"""
import re

from app import db
from app.models import Produto, Rodada, RodadaProduto, Fornecedor


def _csrf(client, url):
    r = client.get(url)
    m = re.search(rb'name="csrf_token"[^>]*value="([^"]+)"', r.data)
    return m.group(1).decode() if m else None


def _cenario_sugestao_pendente():
    """Admin tem rodada em aguardando_cotacao; fornecedor sugeriu produto novo."""
    rodada = Rodada.query.first()
    rodada.status = "aguardando_cotacao"
    forn = Fornecedor.query.first()

    # Produto sugerido: nasce ativo=False (novo contrato)
    p = Produto(nome="Smash 120g", categoria="Carne", subcategoria="Hamburguer",
                unidade="kg", ativo=False, descricao="Sugerido por Forn Teste")
    db.session.add(p)
    db.session.flush()

    rp = RodadaProduto(rodada_id=rodada.id, produto_id=p.id,
                       adicionado_por_fornecedor_id=forn.id, aprovado=None)
    db.session.add(rp)
    db.session.commit()
    return rodada.id, rp.id, p.id


def test_recusar_sugestao_nao_desativa_produto_globalmente(app, client_admin):
    """Regressao: recusar sugestao NAO deve setar produto.ativo=False
    em outras rodadas (bug latente corrigido em f079e72)."""
    rodada_id, rp_id, produto_id = _cenario_sugestao_pendente()
    # Simula que este produto foi aprovado em outro momento (ja ativo globalmente)
    db.session.get(Produto, produto_id).ativo = True
    db.session.commit()

    token = _csrf(client_admin, f"/admin/rodadas/{rodada_id}/aprovar-produtos")
    r = client_admin.post(
        f"/admin/rodadas/{rodada_id}/aprovar-produtos",
        data={"csrf_token": token, "rp_id": rp_id, "acao": "recusar"},
        follow_redirects=False,
    )
    assert r.status_code == 302

    # RodadaProduto marcado como recusado APENAS nesta rodada
    rp = db.session.get(RodadaProduto, rp_id)
    assert rp.aprovado is False

    # Produto global NAO foi afetado
    p = db.session.get(Produto, produto_id)
    assert p.ativo is True, "BUG: recusar sugestao nao deve desativar produto globalmente"


def test_produto_sugerido_nasce_inativo_ate_aprovacao(app, client_admin):
    """Sugestao recem-criada deve ficar ativo=False; admin aprovar ativa."""
    rodada_id, rp_id, produto_id = _cenario_sugestao_pendente()

    # Antes da aprovacao: inativo (nao polui catalogo global)
    assert db.session.get(Produto, produto_id).ativo is False

    token = _csrf(client_admin, f"/admin/rodadas/{rodada_id}/aprovar-produtos")
    r = client_admin.post(
        f"/admin/rodadas/{rodada_id}/aprovar-produtos",
        data={"csrf_token": token, "rp_id": rp_id, "acao": "aprovar"},
        follow_redirects=False,
    )
    assert r.status_code == 302

    # Pos-aprovacao: ativo (entrou no catalogo global)
    assert db.session.get(Produto, produto_id).ativo is True
    assert db.session.get(RodadaProduto, rp_id).aprovado is True


def test_lanchonete_nao_aprova_sugestao(app, client_lanchA):
    """admin_required protege aprovacao de sugestao."""
    rodada_id, rp_id, _ = _cenario_sugestao_pendente()
    r = client_lanchA.post(
        f"/admin/rodadas/{rodada_id}/aprovar-produtos",
        data={"rp_id": rp_id, "acao": "aprovar"},
        follow_redirects=False,
    )
    assert r.status_code == 302
    # Estado nao muda
    assert db.session.get(RodadaProduto, rp_id).aprovado is None
