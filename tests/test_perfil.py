"""Testes da tela /perfil: edicao de dados cadastrais + troca de senha."""
import re
from werkzeug.security import check_password_hash

from app import db
from app.models import Usuario, Lanchonete, Fornecedor


def _get_csrf(client, url):
    r = client.get(url)
    m = re.search(rb'name="csrf_token"[^>]*value="([^"]+)"', r.data)
    return m.group(1).decode() if m else None


def test_perfil_requer_login(client):
    r = client.get("/perfil/", follow_redirects=False)
    assert r.status_code == 302
    assert "/login" in r.headers["Location"]


def test_perfil_lanchonete_renderiza(client_lanchA):
    r = client_lanchA.get("/perfil/")
    assert r.status_code == 200
    # Campos especificos de lanchonete
    assert b"nome_fantasia" in r.data
    # Nao deve mostrar campos de fornecedor
    assert b"razao_social" not in r.data
    assert b"chave_pix" not in r.data


def test_perfil_fornecedor_renderiza(client_forn):
    r = client_forn.get("/perfil/")
    assert r.status_code == 200
    # Campos especificos de fornecedor
    assert b"razao_social" in r.data
    assert b"chave_pix" in r.data
    # Nao deve mostrar campos de lanchonete
    assert b"nome_fantasia" not in r.data


def test_perfil_admin_renderiza(client_admin):
    r = client_admin.get("/perfil/")
    assert r.status_code == 200
    # Admin ve apenas dados basicos
    assert b"nome_responsavel" in r.data
    assert b"nome_fantasia" not in r.data
    assert b"razao_social" not in r.data


def test_lanchonete_edita_proprios_dados(app, client_lanchA):
    csrf = _get_csrf(client_lanchA, "/perfil/")
    client_lanchA.post("/perfil/", data={
        "csrf_token": csrf,
        "nome_responsavel": "Novo Nome",
        "telefone": "(43) 98888-1111",
        "nome_fantasia": "Lanch A Renomeada",
        "cnpj": "99.999.999/0001-99",
        "endereco": "Rua Teste, 100",
        "bairro": "Centro",
        "cidade": "Londrina",
    })

    u = Usuario.query.filter_by(email="lancha@test.com").first()
    assert u.nome_responsavel == "Novo Nome"
    assert u.telefone == "(43) 98888-1111"
    assert u.lanchonete.nome_fantasia == "Lanch A Renomeada"
    assert u.lanchonete.cnpj == "99.999.999/0001-99"
    assert u.lanchonete.endereco == "Rua Teste, 100"


def test_fornecedor_edita_dados_bancarios(app, client_forn):
    csrf = _get_csrf(client_forn, "/perfil/")
    client_forn.post("/perfil/", data={
        "csrf_token": csrf,
        "nome_responsavel": "Forn Teste",
        "telefone": "(43) 99999-2222",
        "razao_social": "Fornec Teste SA",
        "nome_contato": "Joao Silva",
        "telefone_fornecedor": "(43) 3222-0000",
        "cidade": "Londrina",
        "chave_pix": "fornec@test.com",
        "banco": "341",
        "agencia": "1234",
        "conta": "56789-0",
    })

    f = Fornecedor.query.first()
    assert f.razao_social == "Fornec Teste SA"
    assert f.chave_pix == "fornec@test.com"
    assert f.banco == "341"
    assert f.agencia == "1234"
    assert f.conta == "56789-0"


def test_troca_senha_sucesso(app, client_lanchA):
    csrf = _get_csrf(client_lanchA, "/perfil/")
    client_lanchA.post("/perfil/", data={
        "csrf_token": csrf,
        "nome_responsavel": "Teste",
        "telefone": "",
        "nome_fantasia": "Lanch A",
        "senha_atual": "testpass",
        "senha_nova": "nova_senha_forte",
        "senha_confirmacao": "nova_senha_forte",
    })

    u = Usuario.query.filter_by(email="lancha@test.com").first()
    assert check_password_hash(u.senha_hash, "nova_senha_forte")


def test_troca_senha_atual_errada_bloqueia(app, client_lanchA):
    csrf = _get_csrf(client_lanchA, "/perfil/")
    client_lanchA.post("/perfil/", data={
        "csrf_token": csrf,
        "nome_responsavel": "Nome Hacker",
        "telefone": "",
        "nome_fantasia": "Lanch A",
        "senha_atual": "senha_errada",
        "senha_nova": "tentativa123",
        "senha_confirmacao": "tentativa123",
    })

    u = Usuario.query.filter_by(email="lancha@test.com").first()
    # Senha original preservada
    assert check_password_hash(u.senha_hash, "testpass")
    # Rollback tambem desfaz o nome (senha atual errada = nao salva nada)
    assert u.nome_responsavel != "Nome Hacker"


def test_troca_senha_confirmacao_diferente_bloqueia(app, client_lanchA):
    csrf = _get_csrf(client_lanchA, "/perfil/")
    client_lanchA.post("/perfil/", data={
        "csrf_token": csrf,
        "nome_responsavel": "Teste",
        "telefone": "",
        "nome_fantasia": "Lanch A",
        "senha_atual": "testpass",
        "senha_nova": "nova_senha_1",
        "senha_confirmacao": "nova_senha_2",
    })

    u = Usuario.query.filter_by(email="lancha@test.com").first()
    assert check_password_hash(u.senha_hash, "testpass")


def test_troca_senha_curta_bloqueia(app, client_lanchA):
    csrf = _get_csrf(client_lanchA, "/perfil/")
    client_lanchA.post("/perfil/", data={
        "csrf_token": csrf,
        "nome_responsavel": "Teste",
        "telefone": "",
        "nome_fantasia": "Lanch A",
        "senha_atual": "testpass",
        "senha_nova": "curta",
        "senha_confirmacao": "curta",
    })

    u = Usuario.query.filter_by(email="lancha@test.com").first()
    assert check_password_hash(u.senha_hash, "testpass")


def test_lanchonete_A_nao_altera_lanchonete_B(app, client_lanchA):
    """Nao existe rota /perfil/<id> — current_user eh sempre a fonte. Garante que
    POST da lanchonete A nunca toca dados de B mesmo tentando forcar via form."""
    lanchB_id = Usuario.query.filter_by(email="lanchb@test.com").first().lanchonete.id
    nome_original_b = db.session.get(Lanchonete, lanchB_id).nome_fantasia

    csrf = _get_csrf(client_lanchA, "/perfil/")
    # Tenta passar campo 'lanchonete_id' ou 'usuario_id' — rota ignora
    client_lanchA.post("/perfil/", data={
        "csrf_token": csrf,
        "lanchonete_id": lanchB_id,
        "usuario_id": 999,
        "nome_responsavel": "Teste",
        "telefone": "",
        "nome_fantasia": "TENTATIVA DE HIJACK",
    })

    # Lanchonete B intacta
    assert db.session.get(Lanchonete, lanchB_id).nome_fantasia == nome_original_b
    # Lanchonete A renomeada (confirma que rota agiu no current_user)
    u = Usuario.query.filter_by(email="lancha@test.com").first()
    assert u.lanchonete.nome_fantasia == "TENTATIVA DE HIJACK"
