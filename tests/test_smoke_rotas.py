"""Smoke test: todas as rotas GET autenticadas devem responder 200/302
sem erro 500 quando hitadas pelo perfil correto.

Esse teste pega rapido qualquer regressao de template (KeyError, AttributeError,
filter Jinja inexistente, etc). Nao valida CONTEUDO — so que renderiza.
"""
import pytest


# Rotas GET por perfil. (rota, lista de status_codes aceitaveis)
# 200 = renderizou, 302 = redirect (rota com pre-requisito ja conhecido).
ROTAS_LANCHONETE = [
    "/dashboard",
    "/pedidos/",
    "/pedidos/catalogo",  # so renderiza se ha rodada aberta
    "/minhas-rodadas/",
    "/minhas-rodadas/cmv",
    "/minhas-rodadas/analytics",
    "/rodadas/",
    "/perfil/",
]

ROTAS_FORNECEDOR = [
    "/fornecedor/dashboard",
    "/fornecedor/analytics",
    "/fornecedor/pnl",
    "/rodadas/",
    "/perfil/",
]

ROTAS_ADMIN = [
    "/dashboard",
    "/admin/analytics",
    "/admin/relatorio",
    "/admin/historico-aprovacoes",
    "/admin/produtos",
    "/admin/produtos/novo",
    "/admin/fornecedores",
    "/admin/fornecedores/novo",
    "/admin/lanchonetes",
    "/admin/lanchonetes/nova",
    "/admin/rodadas/nova",
    "/rodadas/",
    "/perfil/",
]

ROTAS_PUBLICAS = [
    "/",
    "/login",
    "/registro",
    "/registro/fornecedor",
    "/esqueci-senha",
    "/marketplace",
]


@pytest.mark.parametrize("rota", ROTAS_PUBLICAS)
def test_smoke_publica(app, client, rota):
    """Rota publica nao loga deve responder 200 sem erro."""
    r = client.get(rota, follow_redirects=False)
    assert r.status_code in (200, 302), (
        f"GET {rota} retornou {r.status_code}, esperava 200 ou 302"
    )


@pytest.mark.parametrize("rota", ROTAS_LANCHONETE)
def test_smoke_lanchonete(app, client_lanchA, rota):
    r = client_lanchA.get(rota, follow_redirects=False)
    assert r.status_code in (200, 302), (
        f"GET {rota} (lanchonete) retornou {r.status_code}"
    )


@pytest.mark.parametrize("rota", ROTAS_FORNECEDOR)
def test_smoke_fornecedor(app, client_forn, rota):
    r = client_forn.get(rota, follow_redirects=False)
    assert r.status_code in (200, 302), (
        f"GET {rota} (fornecedor) retornou {r.status_code}"
    )


@pytest.mark.parametrize("rota", ROTAS_ADMIN)
def test_smoke_admin(app, client_admin, rota):
    r = client_admin.get(rota, follow_redirects=False)
    assert r.status_code in (200, 302), (
        f"GET {rota} (admin) retornou {r.status_code}"
    )
