"""Testes de autorizacao/IDOR nos endpoints novos de aprovacao de cotacao
(SubmissaoCotacao + NotaNegociacao).

Cobre gaps identificados depois do commit b5be694 (fluxo aprovacao cotacao final):
1. admin_required protege aprovacao de cotacao
2. fornecedor_required protege tela cotacao-final
3. cotacao aprovada nao pode ser editada pelo fornecedor
4. nota de negociacao nao pode ser adicionada apos aprovacao
5. fornecedor B nao consegue agir sobre submissao de fornecedor A
"""
import re
from datetime import datetime
from werkzeug.security import generate_password_hash

from app import db
from app.models import (
    Usuario, Fornecedor, Lanchonete, Rodada, Produto, RodadaProduto,
    SubmissaoCotacao, NotaNegociacao, ItemPedido, ParticipacaoRodada, Cotacao,
)


def _get_csrf(client, url):
    r = client.get(url)
    m = re.search(rb'name="csrf_token"[^>]*value="([^"]+)"', r.data)
    return m.group(1).decode() if m else None


def _prepara_em_negociacao():
    rodada = Rodada.query.first()
    produto = Produto.query.first()
    lanch = Lanchonete.query.filter_by(nome_fantasia="Lanch A").first()
    forn = Fornecedor.query.first()

    rp = RodadaProduto.query.filter_by(rodada_id=rodada.id, produto_id=produto.id).first()
    if rp:
        rp.preco_partida = 20.00

    db.session.add(ItemPedido(
        rodada_id=rodada.id, lanchonete_id=lanch.id,
        produto_id=produto.id, quantidade=10,
    ))
    db.session.add(ParticipacaoRodada(
        rodada_id=rodada.id, lanchonete_id=lanch.id,
        pedido_enviado_em=datetime.utcnow(),
        pedido_aprovado_em=datetime.utcnow(),
    ))
    rodada.status = "em_negociacao"
    db.session.commit()
    return rodada.id, forn.id, produto.id


def _cria_fornecedor_b_com_cotacao(rodada_id, produto_id, preco=22.00):
    """Cria fornecedor B direto no DB + cotacao dele na rodada.

    Retorna forn_b_id, cot_b_id. Nao precisa autenticar B porque os testes
    validam o comportamento via client do fornecedor A — o isolamento esta
    na rota (filter_by fornecedor_id=current_user.fornecedor.id).
    """
    u = Usuario(
        email="fornb@test.com",
        senha_hash=generate_password_hash("testpass"),
        nome_responsavel="Forn B",
        telefone="(43) 88888-0000",
        tipo="fornecedor",
    )
    db.session.add(u)
    db.session.flush()
    f = Fornecedor(usuario_id=u.id, razao_social="Fornec B")
    db.session.add(f)
    db.session.flush()
    cot = Cotacao(
        rodada_id=rodada_id, fornecedor_id=f.id,
        produto_id=produto_id, preco_unitario=preco,
    )
    db.session.add(cot)
    db.session.commit()
    return f.id, cot.id


# ---------- admin_required protege aprovacao de cotacao ----------

def test_lanchonete_nao_aprova_cotacao(app, client_lanchA):
    rodada_id, forn_id, _ = _prepara_em_negociacao()
    sub = SubmissaoCotacao(rodada_id=rodada_id, fornecedor_id=forn_id,
                            enviada_em=datetime.utcnow())
    db.session.add(sub)
    db.session.commit()
    sub_id = sub.id

    # Lanchonete tenta aprovar — decorator devolve 302 pra main.dashboard
    r = client_lanchA.post(
        f"/admin/rodadas/{rodada_id}/aprovar-cotacoes",
        data={"submissao_id": sub_id, "acao": "aprovar"},
        follow_redirects=False,
    )
    assert r.status_code == 302
    # Estado no DB inalterado
    assert db.session.get(SubmissaoCotacao, sub_id).aprovada_em is None


def test_fornecedor_nao_aprova_cotacao(app, client_forn):
    rodada_id, forn_id, _ = _prepara_em_negociacao()
    sub = SubmissaoCotacao(rodada_id=rodada_id, fornecedor_id=forn_id,
                            enviada_em=datetime.utcnow())
    db.session.add(sub)
    db.session.commit()
    sub_id = sub.id

    r = client_forn.post(
        f"/admin/rodadas/{rodada_id}/aprovar-cotacoes",
        data={"submissao_id": sub_id, "acao": "aprovar"},
        follow_redirects=False,
    )
    assert r.status_code == 302
    assert db.session.get(SubmissaoCotacao, sub_id).aprovada_em is None


def test_lanchonete_nao_adiciona_nota_admin(app, client_lanchA):
    rodada_id, forn_id, _ = _prepara_em_negociacao()
    sub = SubmissaoCotacao(rodada_id=rodada_id, fornecedor_id=forn_id,
                            enviada_em=datetime.utcnow())
    db.session.add(sub)
    db.session.commit()
    sub_id = sub.id

    antes = NotaNegociacao.query.count()
    r = client_lanchA.post(
        f"/admin/submissoes/{sub_id}/nota",
        data={"texto": "nota maliciosa"},
        follow_redirects=False,
    )
    assert r.status_code == 302
    # Nenhuma nota criada
    assert NotaNegociacao.query.count() == antes


# ---------- fornecedor_required protege tela cotacao-final ----------

def test_lanchonete_nao_acessa_cotar_final(app, client_lanchA):
    rodada_id, _, _ = _prepara_em_negociacao()
    r = client_lanchA.get(
        f"/fornecedor/rodada/{rodada_id}/cotacao-final",
        follow_redirects=False,
    )
    assert r.status_code == 302


def test_admin_nao_acessa_cotar_final(app, client_admin):
    rodada_id, _, _ = _prepara_em_negociacao()
    r = client_admin.get(
        f"/fornecedor/rodada/{rodada_id}/cotacao-final",
        follow_redirects=False,
    )
    assert r.status_code == 302


# ---------- cotacao aprovada nao pode ser editada pelo fornecedor ----------

def test_fornecedor_nao_edita_cotacao_aprovada(app, client_forn):
    """Apos admin aprovar, POST do fornecedor nao deve sobrescrever preco."""
    rodada_id, forn_id, produto_id = _prepara_em_negociacao()
    # Cria cotacao existente + submissao JA APROVADA
    cot = Cotacao(
        rodada_id=rodada_id, fornecedor_id=forn_id,
        produto_id=produto_id, preco_unitario=18.00,
    )
    db.session.add(cot)
    sub = SubmissaoCotacao(
        rodada_id=rodada_id, fornecedor_id=forn_id,
        enviada_em=datetime.utcnow(),
        aprovada_em=datetime.utcnow(),
    )
    db.session.add(sub)
    db.session.commit()
    cot_id = cot.id

    token = _get_csrf(client_forn, f"/fornecedor/rodada/{rodada_id}/cotacao-final")
    r = client_forn.post(
        f"/fornecedor/rodada/{rodada_id}/cotacao-final",
        data={
            "csrf_token": token,
            f"preco_final_{produto_id}": "5.00",  # tenta baixar o preco
            "acao": "salvar",
        },
        follow_redirects=False,
    )
    assert r.status_code in (200, 302)

    # Preco NAO mudou (bloqueado=True por aprovada_em)
    assert float(db.session.get(Cotacao, cot_id).preco_unitario) == 18.00


# ---------- nota apos aprovacao eh bloqueada ----------

def test_fornecedor_nao_adiciona_nota_apos_aprovacao(app, client_forn):
    rodada_id, forn_id, _ = _prepara_em_negociacao()
    sub = SubmissaoCotacao(
        rodada_id=rodada_id, fornecedor_id=forn_id,
        enviada_em=datetime.utcnow(),
        aprovada_em=datetime.utcnow(),
    )
    db.session.add(sub)
    db.session.commit()

    antes = NotaNegociacao.query.count()
    token = _get_csrf(client_forn, f"/fornecedor/rodada/{rodada_id}/cotacao-final")
    r = client_forn.post(
        f"/fornecedor/rodada/{rodada_id}/cotacao-final/nota",
        data={"csrf_token": token, "texto": "tentativa depois da aprovacao"},
        follow_redirects=False,
    )
    assert r.status_code in (200, 302)
    assert NotaNegociacao.query.count() == antes


def test_admin_nota_vazia_rejeitada(app, client_admin):
    rodada_id, forn_id, _ = _prepara_em_negociacao()
    sub = SubmissaoCotacao(
        rodada_id=rodada_id, fornecedor_id=forn_id,
        enviada_em=datetime.utcnow(),
    )
    db.session.add(sub)
    db.session.commit()
    sub_id = sub.id

    antes = NotaNegociacao.query.count()
    token = _get_csrf(client_admin, f"/admin/rodadas/{rodada_id}/aprovar-cotacoes")
    r = client_admin.post(
        f"/admin/submissoes/{sub_id}/nota",
        data={"csrf_token": token, "texto": "   "},
        follow_redirects=False,
    )
    assert r.status_code in (200, 302)
    assert NotaNegociacao.query.count() == antes


# ---------- Isolamento entre fornecedores ----------

def test_fornecedor_nao_altera_cotacao_de_outro_fornecedor(app, client_forn):
    """Rota /fornecedor/rodada/<id>/cotacao-final filtra por current_user.fornecedor.id.

    Com cotacao pre-existente do fornecedor B no DB, o POST do fornecedor A
    NAO deve sobrescrever a cotacao de B — deve criar registro novo pra A.
    """
    rodada_id, forn_a_id, produto_id = _prepara_em_negociacao()
    forn_b_id, cot_b_id = _cria_fornecedor_b_com_cotacao(
        rodada_id, produto_id, preco=22.00,
    )

    token = _get_csrf(client_forn, f"/fornecedor/rodada/{rodada_id}/cotacao-final")
    client_forn.post(
        f"/fornecedor/rodada/{rodada_id}/cotacao-final",
        data={"csrf_token": token, f"preco_final_{produto_id}": "7.00",
              "acao": "salvar"},
        follow_redirects=False,
    )

    # Cotacao de B intacta
    cot_b = db.session.get(Cotacao, cot_b_id)
    assert float(cot_b.preco_unitario) == 22.00
    assert cot_b.fornecedor_id == forn_b_id

    # Cotacao de A criada separadamente
    cot_a = Cotacao.query.filter_by(
        rodada_id=rodada_id, fornecedor_id=forn_a_id, produto_id=produto_id,
    ).first()
    assert cot_a is not None
    assert float(cot_a.preco_unitario) == 7.00
    assert cot_a.id != cot_b_id
