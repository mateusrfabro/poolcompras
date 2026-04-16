"""
Seed de demonstracao - cria 10 lanchonetes, 5 fornecedores, 5 rodadas
(1 aberta + 3 finalizadas + 1 cancelada) com pedidos e cotacoes realistas.

Pre-requisito: rodar scripts/seed.py antes (cria admin + produtos).
Idempotente: roda varias vezes sem duplicar.

Rodar: python scripts/seed_demo.py
"""
import sys
import os
import random
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from werkzeug.security import generate_password_hash
from app import create_app, db
from app.models import (
    Usuario, Lanchonete, Fornecedor, Produto,
    Rodada, ItemPedido, Cotacao,
)

app = create_app("development")

# Determinismo: mesma seed = mesmos dados em qualquer maquina
random.seed(42)

LANCHONETES = [
    ("Smash House Londrina", "Carlos Mendes", "(43) 99100-0001", "smash@demo.com",
     "12.345.678/0001-01", "Av. Higienopolis, 1200", "Centro"),
    ("Burger Norte", "Mariana Silva", "(43) 99100-0002", "burgernorte@demo.com",
     "12.345.678/0001-02", "R. Sergipe, 450", "Vila Brasil"),
    ("BurgerLab 43", "Ricardo Tanaka", "(43) 99100-0003", "lab43@demo.com",
     "12.345.678/0001-03", "Av. Maringa, 2300", "Jardim Bandeirantes"),
    ("Hamburgueria do Tio", "Jose Roberto", "(43) 99100-0004", "tio@demo.com",
     "12.345.678/0001-04", "R. Goias, 800", "Centro"),
    ("Vila Burguer", "Patricia Lima", "(43) 99100-0005", "vila@demo.com",
     "12.345.678/0001-05", "Av. Bandeirantes, 1500", "Vila Casoni"),
    ("Black Smash", "Eduardo Ferreira", "(43) 99100-0006", "black@demo.com",
     "12.345.678/0001-06", "R. Parana, 1000", "Centro"),
    ("Burgao da Esquina", "Amanda Costa", "(43) 99100-0007", "esquina@demo.com",
     "12.345.678/0001-07", "Av. Theodoro Victorelli, 200", "Bela Suica"),
    ("Hamburgueteria 9", "Felipe Souza", "(43) 99100-0008", "h9@demo.com",
     "12.345.678/0001-08", "R. Belo Horizonte, 700", "Centro"),
    ("Smash & Co", "Beatriz Oliveira", "(43) 99100-0009", "smashco@demo.com",
     "12.345.678/0001-09", "Av. Saul Elkind, 3000", "Jardim Alvorada"),
    ("Old School Burger", "Marcos Pereira", "(43) 99100-0010", "oldschool@demo.com",
     "12.345.678/0001-10", "R. Quintino Bocaiuva, 500", "Centro"),
]

FORNECEDORES = [
    ("Distribuidora Sul Carnes Ltda", "Helena Martins", "(43) 99200-0001",
     "vendas@dsulcarnes.demo", "Londrina"),
    ("Padaria Industrial Pao Real", "Joao Vitor", "(43) 99200-0002",
     "comercial@paoreal.demo", "Londrina"),
    ("Atacadao Hortifruti Norte", "Sandra Rocha", "(43) 99200-0003",
     "atendimento@hortinorte.demo", "Cambe"),
    ("Bebidas & Cia Distribuidora", "Roberto Camargo", "(43) 99200-0004",
     "vendas@bebidasecia.demo", "Londrina"),
    ("EmbalaTudo Descartaveis", "Luciana Pinto", "(43) 99200-0005",
     "comercial@embalatudo.demo", "Londrina"),
]

# Quem cota o que (por categoria de produto)
FORNECEDOR_CATEGORIAS = {
    "Distribuidora Sul Carnes Ltda": ["Carne", "Bacon/Embutido", "Queijo"],
    "Padaria Industrial Pao Real":   ["Pao"],
    "Atacadao Hortifruti Norte":     ["Vegetal", "Outro"],
    "Bebidas & Cia Distribuidora":   ["Bebida", "Molho"],
    "EmbalaTudo Descartaveis":       ["Embalagem", "Descartavel"],
}

# Faixa de preco base por categoria (BRL/unidade da tabela produtos)
PRECO_BASE = {
    "Carne":           (35.00, 65.00),
    "Pao":             (0.80,  1.80),
    "Queijo":          (40.00, 70.00),
    "Bacon/Embutido":  (32.00, 55.00),
    "Molho":           (12.00, 28.00),
    "Vegetal":         (5.00,  18.00),
    "Bebida":          (28.00, 55.00),
    "Embalagem":       (0.45,  1.20),
    "Descartavel":     (0.10,  6.00),
    "Outro":           (15.00, 30.00),
}


def get_or_create_lanchonete(nome, responsavel, tel, email, cnpj, endereco, bairro):
    user = Usuario.query.filter_by(email=email).first()
    if user:
        return user.lanchonete
    user = Usuario(
        email=email,
        senha_hash=generate_password_hash("demo123"),
        nome_responsavel=responsavel,
        telefone=tel,
        tipo="lanchonete",
        is_admin=False,
    )
    db.session.add(user)
    db.session.flush()
    lanch = Lanchonete(
        usuario_id=user.id,
        nome_fantasia=nome,
        cnpj=cnpj,
        endereco=endereco,
        bairro=bairro,
        cidade="Londrina",
        ativa=True,
    )
    db.session.add(lanch)
    db.session.flush()
    return lanch


def get_or_create_fornecedor(razao, contato, tel, email, cidade):
    user = Usuario.query.filter_by(email=email).first()
    if user:
        return user.fornecedor
    user = Usuario(
        email=email,
        senha_hash=generate_password_hash("demo123"),
        nome_responsavel=contato,
        telefone=tel,
        tipo="fornecedor",
        is_admin=False,
    )
    db.session.add(user)
    db.session.flush()
    forn = Fornecedor(
        usuario_id=user.id,
        razao_social=razao,
        nome_contato=contato,
        telefone=tel,
        email=email,
        cidade=cidade,
        ativo=True,
    )
    db.session.add(forn)
    db.session.flush()
    return forn


def get_or_create_rodada(nome, abertura, fechamento, status):
    rod = Rodada.query.filter_by(nome=nome).first()
    if rod:
        return rod, False
    rod = Rodada(
        nome=nome,
        data_abertura=abertura,
        data_fechamento=fechamento,
        status=status,
    )
    db.session.add(rod)
    db.session.flush()
    return rod, True


def quantidade_realista(categoria):
    """Volume tipico de pedido por categoria."""
    faixas = {
        "Carne":           (5, 25),     # kg
        "Pao":             (50, 300),   # unidades
        "Queijo":          (2, 10),     # kg
        "Bacon/Embutido":  (3, 12),     # kg
        "Molho":           (2, 8),      # kg/litro
        "Vegetal":         (5, 20),     # kg
        "Bebida":          (2, 8),      # caixa/fardo
        "Embalagem":       (100, 500),  # unidades
        "Descartavel":     (50, 300),   # unidades/pacote
        "Outro":           (5, 20),     # kg
    }
    lo, hi = faixas.get(categoria, (1, 10))
    return round(random.uniform(lo, hi), 1)


def popular_pedidos_e_cotacoes(rodada, lanchonetes, fornecedores, produtos, status_final):
    """Cria ItemPedido (todas lanchonetes participando) e Cotacao (so se finalizada)."""
    # Pedidos: cada lanchonete pede 5-15 produtos aleatorios da rodada
    if not ItemPedido.query.filter_by(rodada_id=rodada.id).first():
        for lanch in lanchonetes:
            n_produtos = random.randint(5, 15)
            escolhidos = random.sample(produtos, n_produtos)
            for prod in escolhidos:
                item = ItemPedido(
                    rodada_id=rodada.id,
                    lanchonete_id=lanch.id,
                    produto_id=prod.id,
                    quantidade=quantidade_realista(prod.categoria),
                )
                db.session.add(item)

    # Cotacoes: apenas se rodada esta finalizada (cancelada nao tem cotacoes)
    if status_final == "finalizada":
        if not Cotacao.query.filter_by(rodada_id=rodada.id).first():
            for forn in fornecedores:
                categorias_atende = FORNECEDOR_CATEGORIAS.get(forn.razao_social, [])
                produtos_que_cota = [p for p in produtos if p.categoria in categorias_atende]
                for prod in produtos_que_cota:
                    lo, hi = PRECO_BASE.get(prod.categoria, (10.0, 50.0))
                    preco = round(random.uniform(lo, hi), 2)
                    cot = Cotacao(
                        rodada_id=rodada.id,
                        fornecedor_id=forn.id,
                        produto_id=prod.id,
                        preco_unitario=preco,
                        selecionada=False,
                    )
                    db.session.add(cot)

            # Marcar como "selecionada" a cotacao mais barata por produto
            db.session.flush()
            from sqlalchemy import func
            subq = (
                db.session.query(
                    Cotacao.produto_id,
                    func.min(Cotacao.preco_unitario).label("min_preco"),
                )
                .filter(Cotacao.rodada_id == rodada.id)
                .group_by(Cotacao.produto_id)
                .subquery()
            )
            vencedoras = (
                db.session.query(Cotacao)
                .join(subq, (Cotacao.produto_id == subq.c.produto_id) &
                            (Cotacao.preco_unitario == subq.c.min_preco))
                .filter(Cotacao.rodada_id == rodada.id)
                .all()
            )
            for v in vencedoras:
                v.selecionada = True


def seed():
    with app.app_context():
        db.create_all()

        # Pre-check: produtos precisam existir
        produtos = Produto.query.filter_by(ativo=True).all()
        if not produtos:
            print("ERRO: produtos nao encontrados. Rode scripts/seed.py primeiro.")
            return

        # Lanchonetes
        print("--- Lanchonetes ---")
        lanchonetes = []
        for nome, resp, tel, email, cnpj, end, bairro in LANCHONETES:
            l = get_or_create_lanchonete(nome, resp, tel, email, cnpj, end, bairro)
            lanchonetes.append(l)
            print(f"  {nome}  ({email} / demo123)")

        # Fornecedores
        print("--- Fornecedores ---")
        fornecedores = []
        for razao, contato, tel, email, cidade in FORNECEDORES:
            f = get_or_create_fornecedor(razao, contato, tel, email, cidade)
            fornecedores.append(f)
            print(f"  {razao}  ({email} / demo123)")

        db.session.commit()

        # Rodadas: 1 aberta + 3 finalizadas + 1 cancelada
        hoje = datetime.now(timezone.utc).replace(hour=8, minute=0, second=0, microsecond=0)

        rodadas_def = [
            # (nome, dias_atras, status_final, quem_pede)
            (f"Rodada {(hoje - timedelta(days=0)).strftime('%d/%m')} - Manha", 0, "aberta", lanchonetes[:6]),
            (f"Rodada {(hoje - timedelta(days=1)).strftime('%d/%m')} - Manha", 1, "finalizada", lanchonetes),
            (f"Rodada {(hoje - timedelta(days=3)).strftime('%d/%m')} - Manha", 3, "finalizada", lanchonetes[:8]),
            (f"Rodada {(hoje - timedelta(days=5)).strftime('%d/%m')} - Manha", 5, "cancelada", lanchonetes[:3]),
            (f"Rodada {(hoje - timedelta(days=7)).strftime('%d/%m')} - Manha", 7, "finalizada", lanchonetes[:9]),
        ]

        print("--- Rodadas ---")
        for nome, dias, status_final, quem in rodadas_def:
            abertura = hoje - timedelta(days=dias)
            fechamento = abertura.replace(hour=12, minute=0)  # padrao: fecha 12:00
            rod, criada = get_or_create_rodada(nome, abertura, fechamento, status_final)
            popular_pedidos_e_cotacoes(rod, quem, fornecedores, produtos, status_final)
            marca = "criada" if criada else "ja existia"
            print(f"  {nome}  status={status_final}  ({marca})")

        db.session.commit()
        print("\nSeed demo concluido!")
        print(f"Login lanchonete demo: smash@demo.com / demo123")
        print(f"Login fornecedor demo: vendas@dsulcarnes.demo / demo123")


if __name__ == "__main__":
    seed()