"""Hash de senha com Argon2id (padrao OWASP) + compat com pbkdf2 legacy.

Argon2id eh mais resistente a GPU/ASIC que pbkdf2-sha256 e tem custo
computacional configuravel. Locust mediu POST /login ~4200ms em dev com
pbkdf2 (Werkzeug default 600k iter); Argon2 com params OWASP roda em
~50-100ms.

Migracao gradual: senhas existentes continuam logando via Werkzeug
check_password_hash. No primeiro login bem-sucedido, hash eh atualizado
pra Argon2id (rehash-on-login).

Uso:
    from app.services.passwords import hash_senha, check_senha

    # Cadastro / reset
    user.senha_hash = hash_senha(senha_em_claro)

    # Login
    ok, novo_hash = check_senha(senha, user.senha_hash)
    if ok and novo_hash:
        user.senha_hash = novo_hash
        db.session.commit()
"""
import os

from argon2 import PasswordHasher
from argon2 import exceptions as argon2_exceptions
from werkzeug.security import check_password_hash


# Em testing, params leves pra nao atrasar a suite (269 testes).
# Em prod/dev, defaults proximos do OWASP cheat-sheet (memory_cost 64MB).
def _params_atuais():
    if os.environ.get("PYTEST_CURRENT_TEST") or os.environ.get("FLASK_ENV") == "testing":
        return dict(time_cost=1, memory_cost=8, parallelism=1)
    return dict(time_cost=2, memory_cost=64 * 1024, parallelism=1)


_ph = PasswordHasher(**_params_atuais())


def hash_senha(senha: str) -> str:
    """Hash novo: sempre Argon2id."""
    return _ph.hash(senha)


def check_senha(senha: str, hash_armazenado: str):
    """Valida senha contra hash. Retorna tupla (ok: bool, novo_hash: str|None).

    novo_hash so vem preenchido quando o caller deveria ATUALIZAR o hash:
    - Hash legacy (Werkzeug pbkdf2/scrypt) e senha bate -> upgrade pra Argon2id
    - Hash Argon2id com params antigos -> rehash com params novos

    Senha incorreta -> (False, None) sem distincao.
    """
    if not hash_armazenado:
        return False, None

    if hash_armazenado.startswith("$argon2"):
        try:
            _ph.verify(hash_armazenado, senha)
        except (argon2_exceptions.VerifyMismatchError,
                argon2_exceptions.InvalidHashError,
                argon2_exceptions.VerificationError):
            return False, None
        # Hash valido — checa se params precisam atualizar (ex: time_cost subiu).
        try:
            if _ph.check_needs_rehash(hash_armazenado):
                return True, _ph.hash(senha)
        except argon2_exceptions.InvalidHashError:
            pass
        return True, None

    # Legacy: hash do Werkzeug (pbkdf2:sha256$..., scrypt:..., sha256$...).
    # Se senha bate, faz upgrade pra Argon2id.
    if check_password_hash(hash_armazenado, senha):
        return True, _ph.hash(senha)
    return False, None


# Hash dummy pra equalizar timing em login com email inexistente.
# Computado uma vez no import — evita recalcular a cada tentativa.
_DUMMY_ARGON = _ph.hash("dummy-password-never-matches")


def check_dummy(senha: str) -> None:
    """Faz uma verificacao Argon2 contra hash dummy. Usado pra evitar timing
    attack quando email nao existe — gasta o mesmo tempo de uma verificacao
    real, sem revelar via response time se o usuario existe."""
    try:
        _ph.verify(_DUMMY_ARGON, senha)
    except argon2_exceptions.VerifyMismatchError:
        pass
