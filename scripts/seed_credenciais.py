"""Reseta senhas dos usuarios e renomeia admin pro padrao Aggron pos-rebrand.

Uso (LOCAL DEV):
    python scripts/seed_credenciais.py
    python scripts/seed_credenciais.py --com-demos    # cria smash + dsulcarnes em prod

Uso (SERVIDOR Yggdrasil):
    docker exec -it aggron-app python scripts/seed_credenciais.py
    docker exec -it aggron-app python scripts/seed_credenciais.py --com-demos

Idempotente — pode rodar varias vezes. CRIA admin/Gabriel se nao
existirem (em servidor recem-deployado). Com --com-demos cria tambem
1 lanchonete demo + 1 fornecedor demo pra Mateus testar como esses
perfis no site oficial. Senhas usam Argon2 via app.services.passwords.hash_senha.

Padrao de credenciais documentado:
    adm@aggron.com.br        admin123    (admin — Mateus + Ademar)
    vendas@aggron.com.br     demo123     (vendedor SDR — Gabriel)
    smash@demo.com           demo123     (lanchonete principal)
    vendas@dsulcarnes.demo   demo123     (fornecedor principal)
    @demo.com                demo123     (todos os demais lanchonetes/fornecedores)
"""
import argparse
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app, db
from app.models import Usuario, Vendedor, Lanchonete, Fornecedor
from app.services.passwords import hash_senha


def _garantir_lanchonete_demo(agora):
    """Cria smash@demo.com (lanchonete demo) se nao existir. Idempotente."""
    email = "smash@demo.com"
    u = Usuario.query.filter_by(email=email).first()
    criado = False
    if not u:
        u = Usuario(
            email=email,
            senha_hash=hash_senha("demo123"),
            nome_responsavel="Smash Burger (demo)",
            telefone="(43) 99999-0001",
            tipo="lanchonete",
            senha_atualizada_em=agora,
        )
        db.session.add(u)
        db.session.flush()
        criado = True
        print(f"  CRIADO {email} senha=demo123 (lanchonete demo)")
    else:
        u.senha_hash = hash_senha("demo123")
        u.senha_atualizada_em = agora
        print(f"  RESET  {email} senha=demo123 (lanchonete)")

    lanch = Lanchonete.query.filter_by(usuario_id=u.id).first()
    if not lanch:
        db.session.add(Lanchonete(
            usuario_id=u.id,
            nome_fantasia="Smash Burger Demo",
            cnpj="00.000.000/0001-00",
        ))
        print(f"  + Lanchonete record criado p/ {email}")
    return criado


def _garantir_fornecedor_demo(agora):
    """Cria vendas@dsulcarnes.demo (fornecedor demo) se nao existir."""
    email = "vendas@dsulcarnes.demo"
    u = Usuario.query.filter_by(email=email).first()
    criado = False
    if not u:
        u = Usuario(
            email=email,
            senha_hash=hash_senha("demo123"),
            nome_responsavel="D-Sul Carnes (demo)",
            telefone="(43) 99999-0002",
            tipo="fornecedor",
            senha_atualizada_em=agora,
        )
        db.session.add(u)
        db.session.flush()
        criado = True
        print(f"  CRIADO {email} senha=demo123 (fornecedor demo)")
    else:
        u.senha_hash = hash_senha("demo123")
        u.senha_atualizada_em = agora
        print(f"  RESET  {email} senha=demo123 (fornecedor)")

    forn = Fornecedor.query.filter_by(usuario_id=u.id).first()
    if not forn:
        db.session.add(Fornecedor(
            usuario_id=u.id,
            razao_social="D-Sul Carnes Demo Ltda",
        ))
        print(f"  + Fornecedor record criado p/ {email}")
    return criado


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--com-demos", action="store_true",
                        help="Cria 1 lanchonete demo (smash@demo.com) + 1 fornecedor "
                             "demo (vendas@dsulcarnes.demo) se nao existirem. Util "
                             "pra Mateus testar todos os perfis no servidor.")
    args = parser.parse_args()

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
            admin.tipo = "admin"  # garantia (defesa em profundidade)
            print(f"  RESET  adm@aggron.com.br senha=admin123")
            mudancas += 1
        else:
            admin = Usuario(
                email="adm@aggron.com.br",
                senha_hash=hash_senha("admin123"),
                nome_responsavel="Aggron",
                telefone="(43) 99999-0000",
                tipo="admin",
                senha_atualizada_em=agora,
            )
            db.session.add(admin)
            db.session.flush()
            print(f"  CRIADO adm@aggron.com.br senha=admin123 (admin)")
            mudancas += 1

        # 2) Garante vendedor SDR no email vendas@aggron.com.br
        # Migra gabriel@aggron.com.br -> vendas@aggron.com.br (servidor onde
        # Ademar nao tem mais slot pra criar gabriel@; reaproveita vendas@).
        gabriel_legado = Usuario.query.filter_by(email="gabriel@aggron.com.br").first()
        if gabriel_legado:
            ja_existe = Usuario.query.filter_by(email="vendas@aggron.com.br").first()
            if ja_existe and ja_existe.id != gabriel_legado.id:
                # Edge: alguem ja criou vendas@ via UI — nao sobrescreve.
                print(f"  AVISO  vendas@aggron.com.br ja existe — NAO migrando gabriel@")
            else:
                gabriel_legado.email = "vendas@aggron.com.br"
                print(f"  RENOMEADO gabriel@aggron.com.br -> vendas@aggron.com.br")
                mudancas += 1

        gabriel = Usuario.query.filter_by(email="vendas@aggron.com.br").first()
        if not gabriel:
            gabriel = Usuario(
                email="vendas@aggron.com.br",
                senha_hash=hash_senha("demo123"),
                nome_responsavel="Gabriel",
                telefone="(43) 99999-0000",
                tipo="vendedor",
                senha_atualizada_em=agora,
            )
            db.session.add(gabriel)
            db.session.flush()
            print("  CRIADO vendas@aggron.com.br senha=demo123 (vendedor)")
            mudancas += 1
        else:
            gabriel.senha_hash = hash_senha("demo123")
            gabriel.senha_atualizada_em = agora
            gabriel.tipo = "vendedor"
            print("  RESET  vendas@aggron.com.br senha=demo123")
            mudancas += 1

        v = Vendedor.query.filter_by(usuario_id=gabriel.id).first()
        if not v:
            db.session.add(Vendedor(
                usuario_id=gabriel.id,
                nome="Gabriel",
                meta_mensal_clientes=10,
                ativo=True,
            ))
            print("  + Vendedor record criado p/ Gabriel")
        elif not v.ativo:
            v.ativo = True
            print("  + Vendedor record reativado p/ Gabriel")

        # 3) Reseta senha de todos lanchonetes/fornecedores pra demo123
        for tipo in ("lanchonete", "fornecedor"):
            for u in Usuario.query.filter_by(tipo=tipo).all():
                u.senha_hash = hash_senha("demo123")
                u.senha_atualizada_em = agora
                print(f"  RESET  {u.email:<35} ({tipo})")
                mudancas += 1

        # 4) Opcional: cria perfis demo lanchonete + fornecedor (--com-demos)
        if args.com_demos:
            print()
            print("--- Garantindo perfis demo (--com-demos) ---")
            if _garantir_lanchonete_demo(agora):
                mudancas += 1
            if _garantir_fornecedor_demo(agora):
                mudancas += 1

        db.session.commit()
        print()
        print(f"OK — {mudancas} usuarios atualizados. Logins documentados no docstring.")


if __name__ == "__main__":
    main()
