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

# Tupla: (nome, categoria, subcategoria, unidade, descricao)
PRODUTOS = [
    # Carnes
    ("Blend bovino 180g (congelado)", "Carne", "Hambúrguer", "kg", "Blend 80/20, padrão smash"),
    ("Blend bovino 120g (congelado)", "Carne", "Hambúrguer", "kg", "Blend 80/20, padrão clássico"),
    ("Frango desfiado", "Carne", "Frango", "kg", "Peito de frango cozido e desfiado"),
    ("Costela desfiada", "Carne", "Costela", "kg", "Costela bovina desfiada"),

    # Pães
    ("Pão brioche", "Pão", "Brioche", "unidade", "Pão brioche 10cm, ideal para smash"),
    ("Pão australiano", "Pão", "Australiano", "unidade", "Pão australiano escuro"),
    ("Pão de batata", "Pão", "De Batata", "unidade", "Pão de batata macio"),

    # Queijos
    ("Queijo cheddar fatiado", "Queijo", "Fatiado", "kg", "Cheddar processado, fatias"),
    ("Queijo prato fatiado", "Queijo", "Fatiado", "kg", "Queijo prato, fatias finas"),
    ("Cream cheese", "Queijo", "Cremoso", "kg", "Cream cheese culinário"),

    # Bacon e embutidos
    ("Bacon fatiado", "Bacon/Embutido", "Bacon", "kg", "Bacon suíno fatiado"),
    ("Bacon em cubos", "Bacon/Embutido", "Bacon", "kg", "Bacon em cubos, para crocante"),
    ("Calabresa fatiada", "Bacon/Embutido", "Calabresa", "kg", "Linguiça calabresa fatiada"),

    # Molhos
    ("Maionese balde", "Molho", "Maionese", "kg", "Maionese para base de molhos"),
    ("Ketchup balde", "Molho", "Ketchup", "kg", "Ketchup tradicional"),
    ("Mostarda balde", "Molho", "Mostarda", "kg", "Mostarda amarela"),
    ("Barbecue", "Molho", "Barbecue", "litro", "Molho barbecue"),

    # Vegetais
    ("Alface americana", "Vegetal", "Folha", "kg", "Alface crespa/americana"),
    ("Tomate", "Vegetal", "Tomate", "kg", "Tomate fatiado"),
    ("Cebola roxa", "Vegetal", "Cebola", "kg", "Cebola roxa para anéis"),
    ("Picles em conserva", "Vegetal", "Conserva", "kg", "Picles fatiado em conserva"),
    ("Jalapeño em conserva", "Vegetal", "Conserva", "kg", "Pimenta jalapeño"),

    # Bebidas
    ("Refrigerante lata 350ml (misto)", "Bebida", "Refrigerante", "caixa", "Caixa 12 latas, sabores variados"),
    ("Água mineral 500ml", "Bebida", "Água", "fardo", "Fardo 12 garrafas"),

    # Embalagens
    ("Caixa para hambúrguer", "Embalagem", "Caixa", "unidade", "Caixa kraft, tamanho padrão"),
    ("Saco kraft delivery", "Embalagem", "Kraft", "unidade", "Saco papel kraft com alça"),
    ("Copo descartável 300ml", "Descartável", "Copo", "unidade", "Copo plástico transparente"),
    ("Guardanapo", "Descartável", "Guardanapo", "pacote", "Pacote 100 guardanapos"),

    # Batata / Snack
    ("Batata congelada palito", "Outro", "Batata", "kg", "Batata pré-frita congelada"),
    ("Onion rings congelado", "Outro", "Snack", "kg", "Anéis de cebola empanados"),
]


def seed():
    with app.app_context():
        db.create_all()

        # Admin (vocês)
        if not Usuario.query.filter_by(email="admin@aggron.com.br").first():
            admin = Usuario(
                email="admin@aggron.com.br",
                senha_hash=generate_password_hash("admin123"),
                nome_responsavel="Admin Aggron",
                telefone="(43) 99999-0000",
                tipo="admin",
            )
            db.session.add(admin)
            print("Admin criado: admin@aggron.com.br / admin123")

        # Produtos
        existentes = Produto.query.count()
        if existentes == 0:
            for nome, cat, subcat, unidade, desc in PRODUTOS:
                db.session.add(Produto(
                    nome=nome,
                    categoria=cat,
                    subcategoria=subcat,
                    unidade=unidade,
                    descricao=desc,
                ))
            print(f"{len(PRODUTOS)} produtos cadastrados.")
        else:
            # Atualiza subcategoria dos ja existentes (idempotente)
            por_nome = {p[0]: p[2] for p in PRODUTOS}
            n = 0
            for prod in Produto.query.all():
                if prod.nome in por_nome and not prod.subcategoria:
                    prod.subcategoria = por_nome[prod.nome]
                    n += 1
            if n > 0:
                print(f"{n} produtos existentes ganharam subcategoria.")
            else:
                print(f"Ja existem {existentes} produtos, todos com subcategoria.")

        db.session.commit()
        print("Seed concluído!")


if __name__ == "__main__":
    seed()