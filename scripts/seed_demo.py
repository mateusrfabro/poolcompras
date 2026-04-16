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
    ParticipacaoRodada, AvaliacaoRodada, EventoRodada,
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

# Quem cota o que (por categoria de produto — acentos batem com o seed.py)
FORNECEDOR_CATEGORIAS = {
    "Distribuidora Sul Carnes Ltda": ["Carne", "Bacon/Embutido", "Queijo"],
    "Padaria Industrial Pao Real":   ["P\u00e3o"],
    "Atacadao Hortifruti Norte":     ["Vegetal", "Outro"],
    "Bebidas & Cia Distribuidora":   ["Bebida", "Molho"],
    "EmbalaTudo Descartaveis":       ["Embalagem", "Descart\u00e1vel"],
}

# Faixa de preco base por categoria (BRL/unidade da tabela produtos)
PRECO_BASE = {
    "Carne":           (35.00, 65.00),
    "P\u00e3o":        (0.80,  1.80),
    "Queijo":          (40.00, 70.00),
    "Bacon/Embutido":  (32.00, 55.00),
    "Molho":           (12.00, 28.00),
    "Vegetal":         (5.00,  18.00),
    "Bebida":          (28.00, 55.00),
    "Embalagem":       (0.45,  1.20),
    "Descart\u00e1vel": (0.10,  6.00),
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


# Unidades que NAO aceitam fracao (nao da pra comprar 5.6 fardos de agua)
UNIDADES_DISCRETAS = {"unidade", "caixa", "fardo", "pacote"}


def quantidade_realista(categoria, unidade):
    """Volume tipico de pedido por categoria.
    Respeita o tipo da unidade: discreta -> inteiro; continua (kg/litro) -> 1 casa.
    """
    faixas = {
        "Carne":            (5, 25),    # kg
        "P\u00e3o":         (50, 300),  # unidades
        "Queijo":           (2, 10),    # kg
        "Bacon/Embutido":   (3, 12),    # kg
        "Molho":            (2, 8),     # kg/litro
        "Vegetal":          (5, 20),    # kg
        "Bebida":           (2, 8),     # caixa/fardo
        "Embalagem":        (100, 500), # unidades
        "Descart\u00e1vel": (50, 300),  # unidades/pacote
        "Outro":            (5, 20),    # kg
    }
    lo, hi = faixas.get(categoria, (1, 10))
    valor = random.uniform(lo, hi)
    if unidade in UNIDADES_DISCRETAS:
        return float(int(round(valor)))  # inteiro mas mantem tipo Float do schema
    return round(valor, 1)


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
                    quantidade=quantidade_realista(prod.categoria, prod.unidade),
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


def reset_pedidos_e_cotacoes():
    """Apaga ItemPedido, Cotacao, Participacao, Avaliacao, Evento.
    Preserva usuarios, lanchonetes, fornecedores, produtos, rodadas.
    """
    n_eve = EventoRodada.query.delete()
    n_ava = AvaliacaoRodada.query.delete()
    n_par = ParticipacaoRodada.query.delete()
    n_cot = Cotacao.query.delete()
    n_ped = ItemPedido.query.delete()
    db.session.commit()
    print(f"Reset: {n_ped} pedidos, {n_cot} cotacoes, {n_par} participacoes, "
          f"{n_ava} avaliacoes, {n_eve} eventos removidos.")


def popular_fluxo_finalizado(rodada, lanchonetes, fornecedores, cancelada=False):
    """Cria ParticipacaoRodada + EventoRodada + AvaliacaoRodada para rodadas finalizadas.
    Se cancelada=True: fluxo interrompido cedo; sem avaliacao, sem comprovante, etc.
    """
    from datetime import date
    hoje = datetime.now(timezone.utc)

    # Evento global: pedido_enviado
    if not EventoRodada.query.filter_by(rodada_id=rodada.id,
                                         tipo=EventoRodada.TIPO_RODADA_FECHADA).first():
        db.session.add(EventoRodada(
            rodada_id=rodada.id,
            tipo=EventoRodada.TIPO_RODADA_FECHADA,
            descricao="Rodada fechada para pedidos",
            criado_em=rodada.data_fechamento,
        ))

    if cancelada:
        if not EventoRodada.query.filter_by(rodada_id=rodada.id,
                                             tipo=EventoRodada.TIPO_RODADA_CANCELADA).first():
            db.session.add(EventoRodada(
                rodada_id=rodada.id,
                tipo=EventoRodada.TIPO_RODADA_CANCELADA,
                descricao="Rodada cancelada por volume insuficiente",
                criado_em=rodada.data_fechamento + timedelta(hours=2),
            ))
        # Cria participacoes sem avancar fases
        for lanch in lanchonetes:
            if not ParticipacaoRodada.query.filter_by(
                    rodada_id=rodada.id, lanchonete_id=lanch.id).first():
                db.session.add(ParticipacaoRodada(
                    rodada_id=rodada.id,
                    lanchonete_id=lanch.id,
                ))
        return

    # Rodada finalizada: fluxo completo
    # Evento: cotacao_enviada
    if not EventoRodada.query.filter_by(rodada_id=rodada.id,
                                         tipo=EventoRodada.TIPO_PROPOSTA_CONSOLIDADA).first():
        db.session.add(EventoRodada(
            rodada_id=rodada.id,
            tipo=EventoRodada.TIPO_PROPOSTA_CONSOLIDADA,
            descricao=f"Proposta consolidada com {len(fornecedores)} fornecedores",
            criado_em=rodada.data_fechamento + timedelta(hours=3),
        ))
        db.session.add(EventoRodada(
            rodada_id=rodada.id,
            tipo=EventoRodada.TIPO_RODADA_FINALIZADA,
            descricao="Rodada finalizada com sucesso",
            criado_em=rodada.data_fechamento + timedelta(days=3),
        ))

    # Pra cada lanchonete: participacao em estagio variavel (demo realista)
    # Distribuicao por rodada mais recente (ainda em andamento):
    #   20% aguardando aceite | 15% aceitou, sem comprovante | 15% comprovante enviado, sem confirmacao
    #   10% pag confirmado, sem entrega | 5% entrega informada sem recebimento
    #   35% fluxo completo | 5% problema na entrega
    # Para rodadas antigas: quase tudo completo.
    # Comparacao naive: remove tzinfo pra casar com o que SQLite retorna
    agora_naive = datetime.now(timezone.utc).replace(tzinfo=None)
    fech = rodada.data_fechamento.replace(tzinfo=None) if rodada.data_fechamento.tzinfo else rodada.data_fechamento
    eh_recente = fech >= (agora_naive - timedelta(days=2))

    for i, lanch in enumerate(lanchonetes):
        if ParticipacaoRodada.query.filter_by(
                rodada_id=rodada.id, lanchonete_id=lanch.id).first():
            continue

        perfil = random.random()
        base_dt = rodada.data_fechamento + timedelta(hours=3)

        part = ParticipacaoRodada(rodada_id=rodada.id, lanchonete_id=lanch.id)

        # Estagio 1: aguardando aceite
        if eh_recente and perfil < 0.20:
            db.session.add(part)
            continue
        # Estagio 2: aceitou, sem comprovante
        part.aceite_proposta = True
        part.aceite_em = base_dt + timedelta(hours=2)
        if eh_recente and perfil < 0.35:
            db.session.add(part)
            db.session.flush()
            db.session.add(EventoRodada(
                rodada_id=rodada.id, lanchonete_id=lanch.id,
                tipo=EventoRodada.TIPO_PROPOSTA_ACEITA,
                descricao="Cliente aceitou a proposta final",
                criado_em=part.aceite_em,
            ))
            continue
        # Estagio 3: comprovante enviado, fornecedor nao confirmou
        part.comprovante_key = f"comprovantes/demo/rodada_{rodada.id}_lanch_{lanch.id}.pdf"
        part.comprovante_em = base_dt + timedelta(hours=5)
        if eh_recente and perfil < 0.50:
            db.session.add(part)
            db.session.flush()
            for tipo, desc, dt in [
                (EventoRodada.TIPO_PROPOSTA_ACEITA, "Cliente aceitou a proposta final", part.aceite_em),
                (EventoRodada.TIPO_COMPROVANTE_ENVIADO, "Comprovante de pagamento enviado", part.comprovante_em),
            ]:
                db.session.add(EventoRodada(rodada_id=rodada.id, lanchonete_id=lanch.id,
                                             tipo=tipo, descricao=desc, criado_em=dt))
            continue
        # Estagio 4: pagamento confirmado, sem entrega
        part.pagamento_confirmado_em = base_dt + timedelta(hours=8)
        if eh_recente and perfil < 0.60:
            db.session.add(part)
            db.session.flush()
            for tipo, desc, dt in [
                (EventoRodada.TIPO_PROPOSTA_ACEITA, "Cliente aceitou a proposta final", part.aceite_em),
                (EventoRodada.TIPO_COMPROVANTE_ENVIADO, "Comprovante de pagamento enviado", part.comprovante_em),
                (EventoRodada.TIPO_PAGAMENTO_CONFIRMADO, "Fornecedor confirmou recebimento do pagamento", part.pagamento_confirmado_em),
            ]:
                db.session.add(EventoRodada(rodada_id=rodada.id, lanchonete_id=lanch.id,
                                             tipo=tipo, descricao=desc, criado_em=dt))
            continue
        # Estagio 5 em diante: entrega informada
        part.entrega_informada_em = base_dt + timedelta(days=1, hours=10)
        part.entrega_data = (base_dt + timedelta(days=2)).date()

        # 5% reporta problema, resto confirma OK
        if perfil < 0.05:
            part.recebimento_ok = False
            part.recebimento_em = base_dt + timedelta(days=2, hours=14)
            part.recebimento_observacao = "Faltou 1 kg de bacon fatiado no recebimento"
            part.avaliacao_geral = 2  # problema = nota baixa
            part.avaliacao_em = base_dt + timedelta(days=2, hours=15)
        elif perfil < 0.90:
            # 85% confirma OK e avalia entre 4 e 5
            part.recebimento_ok = True
            part.recebimento_em = base_dt + timedelta(days=2, hours=14)
            part.avaliacao_geral = random.choice([4, 4, 4, 5, 5])
            part.avaliacao_em = base_dt + timedelta(days=2, hours=15)
        # 10% restante: confirma OK mas nao avalia ainda
        else:
            part.recebimento_ok = True
            part.recebimento_em = base_dt + timedelta(days=2, hours=14)

        db.session.add(part)
        db.session.flush()

        # Cria eventos correspondentes para timeline
        eventos = [
            (EventoRodada.TIPO_PROPOSTA_ACEITA,
             "Cliente aceitou a proposta final", part.aceite_em),
            (EventoRodada.TIPO_COMPROVANTE_ENVIADO,
             "Comprovante de pagamento enviado", part.comprovante_em),
            (EventoRodada.TIPO_PAGAMENTO_CONFIRMADO,
             "Fornecedor confirmou recebimento do pagamento", part.pagamento_confirmado_em),
            (EventoRodada.TIPO_ENTREGA_INFORMADA,
             f"Fornecedor informou entrega para {part.entrega_data.strftime('%d/%m/%Y')}",
             part.entrega_informada_em),
        ]
        if part.recebimento_em:
            if part.recebimento_ok:
                eventos.append((EventoRodada.TIPO_RECEBIMENTO_CONFIRMADO,
                                "Cliente confirmou recebimento OK", part.recebimento_em))
            else:
                eventos.append((EventoRodada.TIPO_RECEBIMENTO_PROBLEMA,
                                part.recebimento_observacao, part.recebimento_em))
        if part.avaliacao_em:
            eventos.append((EventoRodada.TIPO_AVALIACAO_ENVIADA,
                            f"Cliente avaliou com {part.avaliacao_geral} estrelas",
                            part.avaliacao_em))

        for tipo, desc, dt in eventos:
            db.session.add(EventoRodada(
                rodada_id=rodada.id,
                lanchonete_id=lanch.id,
                tipo=tipo,
                descricao=desc,
                criado_em=dt,
            ))

        # AvaliacaoRodada: se nota geral >= 4, replica pra todos fornecedores (opcao D)
        # se nota <= 3, cria nota individual por fornecedor (aqui simulado com variacao)
        if part.avaliacao_geral:
            if part.avaliacao_geral >= 4:
                for forn in fornecedores:
                    db.session.add(AvaliacaoRodada(
                        rodada_id=rodada.id,
                        lanchonete_id=lanch.id,
                        fornecedor_id=forn.id,
                        estrelas=part.avaliacao_geral,
                    ))
            else:
                # Opcao D detalhada: 1 fornecedor "problematico" recebe nota baixa
                forn_ruim = random.choice(fornecedores)
                for forn in fornecedores:
                    estrelas = part.avaliacao_geral if forn.id == forn_ruim.id else 4
                    db.session.add(AvaliacaoRodada(
                        rodada_id=rodada.id,
                        lanchonete_id=lanch.id,
                        fornecedor_id=forn.id,
                        estrelas=estrelas,
                        comentario="Problema na entrega" if forn.id == forn_ruim.id else None,
                    ))


def seed(reset=False):
    with app.app_context():
        db.create_all()
        if reset:
            reset_pedidos_e_cotacoes()

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
            # Fase 2: popular fluxo (participacoes, eventos, avaliacoes) em rodadas finalizadas/canceladas
            if status_final == "finalizada":
                popular_fluxo_finalizado(rod, quem, fornecedores, cancelada=False)
            elif status_final == "cancelada":
                popular_fluxo_finalizado(rod, quem, fornecedores, cancelada=True)
            marca = "criada" if criada else "ja existia"
            print(f"  {nome}  status={status_final}  ({marca})")

        db.session.commit()
        print("\nSeed demo concluido!")
        print(f"Login lanchonete demo: smash@demo.com / demo123")
        print(f"Login fornecedor demo: vendas@dsulcarnes.demo / demo123")


if __name__ == "__main__":
    import sys as _sys
    reset_flag = "--reset-pedidos" in _sys.argv
    seed(reset=reset_flag)