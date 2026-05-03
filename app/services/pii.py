"""Helpers pra log seguro de PII (LGPD-friendly).

Centraliza padroes de mascara/redacao usados em multiplos pontos do app
(auth, admin, perfil) pra evitar duplicacao + lazy import circular.
"""


def mask_email(email: str) -> str:
    """Mask de email pra log: 'mateus@gmail.com' -> 'm***@gmail.com'.

    Mantem dominio (util pra correlacao de abuse por dominio) e 1a letra
    do local (util pra correlacao de mesmo user em multiplas linhas de log).
    Resto eh redacted.

    Returns '?' quando entrada eh vazia ou nao parece email.
    """
    if not email or "@" not in email:
        return "?"
    local, dominio = email.split("@", 1)
    inicial = local[0] if local else "?"
    return f"{inicial}***@{dominio}"
