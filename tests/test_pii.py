"""Testes do helper PII (LGPD): mask_email.

Todo log que cita usuario por email PASSA por mask_email — qualquer
regressao aqui = vazamento de PII em log de auditoria/Sentry/Cloudflare.
"""
import pytest

from app.services.pii import mask_email


@pytest.mark.parametrize("entrada,esperado", [
    ("mateus@gmail.com",            "m***@gmail.com"),
    ("ademar@aggron.com.br",        "a***@aggron.com.br"),
    ("smash@demo.com",              "s***@demo.com"),
    ("a@b.co",                      "a***@b.co"),
    ("vendas+ofertas@fornec.demo",  "v***@fornec.demo"),
])
def test_mask_email_padrao_aggron(entrada, esperado):
    """Mantem 1a letra + dominio inteiro; resto do local vai pra ***."""
    assert mask_email(entrada) == esperado


@pytest.mark.parametrize("entrada", [
    "",
    None,
    "semarroba",
    "abc",
])
def test_mask_email_sem_arroba_vira_interrogacao(entrada):
    """Entrada sem '@' retorna '?' — defensivo, nao levanta excecao."""
    assert mask_email(entrada) == "?"


def test_mask_email_local_vazio_apos_arroba():
    """Edge: '@dominio.com' tem local vazio mas eh tecnicamente parseavel
    pelo split. Verifica que o helper trata sem crash."""
    out = mask_email("@dominio.com")
    # Pode ser '?' ou '?***@dominio.com' dependendo da impl — o que importa
    # eh nao crashar e nao vazar um email aparentemente valido.
    assert "@" not in out or out.startswith("?")


def test_mask_email_dominio_preservado():
    """Dominio inteiro fica visivel (correlacao por dominio em incidente)."""
    out = mask_email("usuariolongo.com.completo+tag@subdominio.empresa.com.br")
    assert out.endswith("@subdominio.empresa.com.br")
    # Local mascarado: nao expoe nome completo
    assert "usuariolongo" not in out
    assert "+tag" not in out


def test_mask_email_unicode_funciona():
    """Email com caractere nao-ASCII no local — nao deve crashar."""
    out = mask_email("joão@dominio.com")
    assert out == "j***@dominio.com"
