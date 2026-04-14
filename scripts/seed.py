"""
Seed inicial - cria admin + produtos padrão de hamburgueria.
Rodar: python scripts/seed.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from werkzeug.security import generate_password_hash
from app import create_app, db
from app.models import Usuario, Produto

app = create_app("development")

PRODUTOS = [
    # Carnes
    ("Blend bovino 180g (congelado)", "Carne", "kg", "Blend 80/20, padrão smash"),
    ("Blend bovino 120g (congelado)", "Carne", "kg", "Blend 80/20, padrão clássico"),
    ("Frango desfiado", "Carne", "kg", "Peito de frango cozido e desfiado"),
    ("Costela desfiada", "Carne", "kg", "Costela bovina desfiada"),

    # Pães
    ("Pão brioche", "Pão", "unidade", "Pão brioche 10cm, ideal para smash"),
    ("Pão australiano", "Pão", "unidade", "Pão australiano escuro"),
    ("Pão de batata", "Pão", "unidade", "Pão de batata macio"),

    # Queijos
    ("Queijo cheddar fatiado", "Queijo", "kg", "Cheddar processado, fatias"),
    ("Queijo prato fatiado", "Queijo", "kg", "Queijo prato, fatias finas"),
    ("Cream cheese", "Queijo", "kg", "Cream cheese culinário"),

    # Bacon e embutidos
    ("Bacon fatiado", "Bacon/Embutido", "kg", "Bacon suíno fatiado"),
    ("Bacon em cubos", "Bacon/Embutido", "kg", "Bacon em cubos, para crocante"),
    ("Calabresa fatiada", "Bacon/Embutido", "kg", "Linguiça calabresa fatiada"),

    # Molhos
    ("Maionese balde", "Molho", "kg", "Maionese para base de molhos"),
    ("Ketchup balde", "Molho", "kg", "Ketchup tradicional"),
    ("Mostarda balde", "Molho", "kg", "Mostarda amarela"),
    ("Barbecue", "Molho", "litro", "Molho barbecue"),

    # Vegetais
    ("Alface americana", "Vegetal", "kg", "Alface crespa/americana"),
    ("Tomate", "Vegetal", "kg", "Tomate fatiado"),
    ("Cebola roxa", "Vegetal", "kg", "Cebola roxa para anéis"),
    ("Picles em conserva", "Vegetal", "kg", "Picles fatiado em conserva"),
    ("Jalapeño em conserva", "Vegetal", "kg", "Pimenta jalapeño"),

    # Bebidas
    ("Refrigerante lata 350ml (misto)", "Bebida", "caixa", "Caixa 12 latas, sabores variados"),
    ("Água mineral 500ml", "Bebida", "fardo", "Fardo 12 garrafas"),

    # Embalagens
    ("Caixa para hambúrguer", "Embalagem", "unidade", "Caixa kraft, tamanho padrão"),
    ("Saco kraft delivery", "Embalagem", "unidade", "Saco papel kraft com alça"),
    ("Copo descartável 300ml", "Descartável", "unidade", "Copo plástico transparente"),
    ("Guardanapo", "Descartável", "pacote", "Pacote 100 guardanapos"),

    # Batata
    ("Batata congelada palito", "Outro", "kg", "Batata pré-frita congelada"),
    ("Onion rings congelado", "Outro", "kg", "Anéis de cebola empanados"),
]


def seed():
    with app.app_context():
        db.create_all()

        # Admin (vocês)
        if not Usuario.query.filter_by(email="admin@poolcompras.com").first():
            admin = Usuario(
                email="admin@poolcompras.com",
                senha_hash=generate_password_hash("admin123"),
                nome_responsavel="Admin PoolCompras",
                telefone="(43) 99999-0000",
                tipo="admin",
                is_admin=True,
            )
            db.session.add(admin)
            print("Admin criado: admin@poolcompras.com / admin123")

        # Produtos
        existentes = Produto.query.count()
        if existentes == 0:
            for nome, cat, unidade, desc in PRODUTOS:
                db.session.add(Produto(
                    nome=nome,
                    categoria=cat,
                    unidade=unidade,
                    descricao=desc,
                ))
            print(f"{len(PRODUTOS)} produtos cadastrados.")
        else:
            print(f"Já existem {existentes} produtos. Seed ignorado.")

        db.session.commit()
        print("Seed concluído!")


if __name__ == "__main__":
    seed()