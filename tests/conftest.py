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
from app.models import Usuario, Lanchonete, Fornecedor, Produto, Rodada


@pytest.fixture
def app():
    """App Flask em modo teste com SQLite em arquivo temporario.

    Arquivo (nao :memory:) para evitar problema de connection isolation: cada
    connection a :memory: ve um DB vazio. Com arquivo, todas as connections
    do pool veem o mesmo DB.
    """
    fd, db_path = tempfile.mkstemp(suffix=".db", prefix="poolcompras-test-")
    os.close(fd)
    os.environ["SECRET_KEY"] = "test-secret"  # caso algum lugar cheque

    app = create_app("testing")
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{db_path}"

    # Desabilita rate limiter em testes (evita 429 em varredura rapida)
    limiter.enabled = False

    with app.app_context():
        db.create_all()
        _seed_minimo()
        yield app
        db.session.remove()
        db.drop_all()

    limiter.enabled = True  # reativa para proximos runs
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
    db.session.add(Produto(nome="Blend 180g", categoria="Carne", unidade="kg"))

    # Rodada aberta
    from datetime import datetime, timedelta
    agora = datetime.utcnow()
    db.session.add(Rodada(
        nome="Rodada Teste",
        data_abertura=agora,
        data_fechamento=agora + timedelta(hours=6),
        status="aberta",
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
