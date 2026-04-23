"""
Fixtures pytest para PoolCompras.

Usa SQLite in-memory por teste (isolado), cria schema via db.create_all()
e popula com usuarios fixos para cenarios de IDOR e fluxo.
"""
import os
import tempfile
import pytest
from werkzeug.security import generate_password_hash

from app import create_app, db, limiter
from app.models import Usuario, Lanchonete, Fornecedor, Produto, Rodada, RodadaProduto


@pytest.fixture
def app():
    """App Flask em modo teste com SQLite em arquivo temporario.

    Define TEST_DATABASE_URL ANTES de create_app para garantir que o SQLAlchemy
    seja inicializado apontando pro DB de teste — NUNCA toca o DB de producao/dev.
    Arquivo (nao :memory:) para evitar connection isolation em pools.
    """
    fd, db_path = tempfile.mkstemp(suffix=".db", prefix="poolcompras-test-")
    os.close(fd)
    # IMPORTANTE: setar ANTES do create_app. TestingConfig le TEST_DATABASE_URL.
    os.environ["TEST_DATABASE_URL"] = f"sqlite:///{db_path}"
    os.environ["SECRET_KEY"] = "test-secret"

    app = create_app("testing")
    # Double-check: garante que nao tem URI apontando pro DB real
    uri = app.config["SQLALCHEMY_DATABASE_URI"]
    assert "poolcompras.db" not in uri, (
        f"SEGURANCA: testes nao devem tocar DB real. URI={uri}"
    )

    # Desabilita rate limiter em testes (evita 429 em varredura rapida)
    limiter.enabled = False

    with app.app_context():
        db.create_all()
        _seed_minimo()
        yield app
        db.session.remove()
        db.drop_all()

    limiter.enabled = True  # reativa para proximos runs
    os.environ.pop("TEST_DATABASE_URL", None)
    try:
        os.unlink(db_path)
    except OSError:
        pass


def _seed_minimo():
    """Cria 2 lanchonetes, 1 fornecedor, 1 admin, 1 produto, 1 rodada."""
    def novo_usuario(email, tipo, senha="testpass", admin=False):
        u = Usuario(
            email=email,
            senha_hash=generate_password_hash(senha),
            nome_responsavel="Teste",
            telefone="(43) 99999-0000",
            tipo=tipo,
            is_admin=admin,
        )
        db.session.add(u)
        db.session.flush()
        return u

    # Admin
    novo_usuario("admin@test.com", "admin", admin=True)

    # Lanchonete A
    u1 = novo_usuario("lancha@test.com", "lanchonete")
    db.session.add(Lanchonete(usuario_id=u1.id, nome_fantasia="Lanch A",
                               cnpj="11.111.111/0001-11"))

    # Lanchonete B
    u2 = novo_usuario("lanchb@test.com", "lanchonete")
    db.session.add(Lanchonete(usuario_id=u2.id, nome_fantasia="Lanch B",
                               cnpj="22.222.222/0001-22"))

    # Fornecedor
    uf = novo_usuario("forn@test.com", "fornecedor")
    db.session.add(Fornecedor(usuario_id=uf.id, razao_social="Fornec Teste"))

    # Produto
    produto = Produto(nome="Blend 180g", categoria="Carne", subcategoria="Hamburguer", unidade="kg")
    db.session.add(produto)

    # Rodada aberta
    from datetime import datetime, timedelta, timezone
    agora = datetime.now(timezone.utc)
    rodada = Rodada(
        nome="Rodada Teste",
        data_abertura=agora,
        data_fechamento=agora + timedelta(hours=6),
        status="aberta",
    )
    db.session.add(rodada)
    db.session.flush()

    # Catalogo da rodada (necessario pra lanchonete conseguir pedir)
    db.session.add(RodadaProduto(
        rodada_id=rodada.id, produto_id=produto.id,
    ))

    db.session.commit()


@pytest.fixture
def client(app):
    return app.test_client()


def _login(client, email, senha="testpass"):
    return client.post("/login", data={"email": email, "senha": senha},
                       follow_redirects=False)


# Cada fixture cria SEU PROPRIO test_client para evitar sobrescrita de sessao
# quando um teste recebe dois fixtures de cliente (ex: client_lanchA + client_lanchB)

@pytest.fixture
def client_admin(app):
    c = app.test_client()
    _login(c, "admin@test.com")
    return c


@pytest.fixture
def client_lanchA(app):
    c = app.test_client()
    _login(c, "lancha@test.com")
    return c


@pytest.fixture
def client_lanchB(app):
    c = app.test_client()
    _login(c, "lanchb@test.com")
    return c


@pytest.fixture
def client_forn(app):
    c = app.test_client()
    _login(c, "forn@test.com")
    return c
