"""Reseta senhas dos usuarios e renomeia admin pro padrao Aggron pos-rebrand.

Uso (LOCAL DEV):
    python scripts/seed_credenciais.py

Uso (SERVIDOR Yggdrasil):
    docker exec -it aggron-app python scripts/seed_credenciais.py

Idempotente — pode rodar varias vezes. Cria Gabriel (vendedor SDR) se nao
existir. Senhas usam Argon2 via app.services.passwords.hash_senha.

Padrao de credenciais documentado:
    adm@aggron.com.br        admin123    (admin — Mateus + Ademar)
    gabriel@aggron.com.br    demo123     (vendedor SDR)
    smash@demo.com           demo123     (lanchonete principal)
    vendas@dsulcarnes.demo   demo123     (fornecedor principal)
    @demo.com                demo123     (todos os demais lanchonetes/fornecedores)
"""
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app, db
from app.models import Usuario, Vendedor
from app.services.passwords import hash_senha


def main():
    app = create_app(os.environ.get("FLASK_CONFIG", "default"))
    with app.app_context():
        agora = datetime.now(timezone.utc)
        mudancas = 0

        # 1) Renomeia admin legado se existir; reseta senha pra admin123
        legado = Usuario.query.filter_by(email="admin@poolcompras.com").first()
        if legado:
            legado.email = "adm@aggron.com.br"
            print(f"  RENOMEADO admin@poolcompras.com -> adm@aggron.com.br")
            mudancas += 1

        admin = Usuario.query.filter_by(email="adm@aggron.com.br").first()
        if admin:
            admin.senha_hash = hash_senha("admin123")
            admin.senha_atualizada_em = agora
            print(f"  RESET adm@aggron.com.br senha=admin123")
            mudancas += 1
        else:
            print("  AVISO admin adm@aggron.com.br nao existe — criar manualmente via UI")

        # 2) Garante Gabriel (vendedor SDR)
        gabriel = Usuario.query.filter_by(email="gabriel@aggron.com.br").first()
        if not gabriel:
            gabriel = Usuario(
                email="gabriel@aggron.com.br",
                senha_hash=hash_senha("demo123"),
                nome_responsavel="Gabriel",
                telefone="(43) 99999-0000",
                tipo="vendedor",
                senha_atualizada_em=agora,
            )
            db.session.add(gabriel)
            db.session.flush()
            print("  CRIADO gabriel@aggron.com.br senha=demo123 (vendedor)")
            mudancas += 1
        else:
            gabriel.senha_hash = hash_senha("demo123")
            gabriel.senha_atualizada_em = agora
            gabriel.tipo = "vendedor"
            print("  RESET gabriel@aggron.com.br senha=demo123")
            mudancas += 1

        v = Vendedor.query.filter_by(usuario_id=gabriel.id).first()
        if not v:
            db.session.add(Vendedor(
                usuario_id=gabriel.id,
                nome="Gabriel",
                meta_mensal_clientes=10,
                ativo=True,
            ))
            print("  CRIADO Vendedor record p/ Gabriel")
        elif not v.ativo:
            v.ativo = True
            print("  REATIVADO Vendedor record p/ Gabriel")

        # 3) Reseta senha de todos lanchonetes/fornecedores pra demo123
        for tipo in ("lanchonete", "fornecedor"):
            for u in Usuario.query.filter_by(tipo=tipo).all():
                u.senha_hash = hash_senha("demo123")
                u.senha_atualizada_em = agora
                print(f"  RESET {u.email:<35} ({tipo})")
                mudancas += 1

        db.session.commit()
        print()
        print(f"OK — {mudancas} usuarios atualizados. Logins documentados no docstring deste script.")


if __name__ == "__main__":
    main()
