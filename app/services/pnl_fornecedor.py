"""Calculo do P&L (receita/margem) do fornecedor logado.

Espelha cmv_lanchonete.py, mas do lado oposto da relacao: soma vendas
efetivas (cotacoes selecionadas × volumes aceitos) agrupadas por cliente,
produto e rodada.

Regra: so conta linhas onde (a) Cotacao.selecionada=True e (b) a lanchonete
dona do ItemPedido aceitou a proposta (aceite_proposta=True). Isso garante
paridade com o que aparece no CMV da lanchonete — o somatorio de CMV de
todas lanchonetes = soma dos P&L de todos fornecedores.
"""
from collections import defaultdict
from app import db
from app.models import (
    Rodada, Produto, Lanchonete, ItemPedido, Cotacao, RodadaProduto,
    ParticipacaoRodada,
)


def calcular_pnl(fornecedor_id: int) -> dict:
    """Retorna dict com KPIs, top clientes, top produtos e receita por rodada.

    Esquema:
    {
        "kpis": {"receita_total", "ticket_medio", "rodadas_vendidas",
                 "margem_vs_partida", "margem_vs_partida_pct"},
        "top_clientes": [(nome, gasto, itens, pct)],
        "top_produtos": [(nome, unidade, qtd, receita, preco_medio)],
        "por_rodada":   [{rodada_id, rodada_nome, data, receita, itens, clientes}],
    }

    margem_vs_partida = receita final - receita que teria sido com preco_partida
    (positivo = fornecedor manteve margem apertando menos que o esperado).
    """
    linhas = (
        db.session.query(
            Rodada.id.label("rodada_id"),
            Rodada.nome.label("rodada_nome"),
            Rodada.data_abertura.label("data"),
            Produto.id.label("produto_id"),
            Produto.nome.label("produto_nome"),
            Produto.unidade.label("unidade"),
            Lanchonete.id.label("lanchonete_id"),
            Lanchonete.nome_fantasia.label("cliente"),
            ItemPedido.quantidade.label("quantidade"),
            Cotacao.preco_unitario.label("preco_final"),
            RodadaProduto.preco_partida.label("preco_partida"),
        )
        .join(ItemPedido, ItemPedido.rodada_id == Rodada.id)
        .join(Lanchonete, Lanchonete.id == ItemPedido.lanchonete_id)
        .join(ParticipacaoRodada,
              (ParticipacaoRodada.rodada_id == ItemPedido.rodada_id) &
              (ParticipacaoRodada.lanchonete_id == ItemPedido.lanchonete_id))
        .join(Produto, Produto.id == ItemPedido.produto_id)
        .join(Cotacao,
              (Cotacao.rodada_id == ItemPedido.rodada_id) &
              (Cotacao.produto_id == ItemPedido.produto_id) &
              (Cotacao.fornecedor_id == fornecedor_id) &
              (Cotacao.selecionada.is_(True)))
        .outerjoin(RodadaProduto,
                   (RodadaProduto.rodada_id == ItemPedido.rodada_id) &
                   (RodadaProduto.produto_id == ItemPedido.produto_id))
        .filter(ParticipacaoRodada.aceite_proposta.is_(True))
        .order_by(Rodada.data_abertura.desc(), Produto.nome)
        .all()
    )

    receita_total = 0.0
    receita_seria_partida = 0.0
    receita_por_cliente = defaultdict(lambda: {"gasto": 0.0, "itens": 0})
    por_produto = defaultdict(lambda: {"nome": "", "unidade": "",
                                         "qtd": 0.0, "receita": 0.0})
    por_rodada = {}

    for l in linhas:
        qtd = float(l.quantidade or 0)
        final = float(l.preco_final or 0)
        partida = float(l.preco_partida) if l.preco_partida else final
        receita = qtd * final
        receita_partida = qtd * partida

        receita_total += receita
        receita_seria_partida += receita_partida

        c = receita_por_cliente[l.lanchonete_id]
        c["gasto"] += receita
        c["itens"] += 1
        c["nome"] = l.cliente

        p = por_produto[l.produto_id]
        p["nome"] = l.produto_nome
        p["unidade"] = l.unidade
        p["qtd"] += qtd
        p["receita"] += receita

        r = por_rodada.setdefault(l.rodada_id, {
            "rodada_id": l.rodada_id,
            "rodada_nome": l.rodada_nome,
            "data": l.data,
            "receita": 0.0,
            "itens": 0,
            "clientes": set(),
        })
        r["receita"] += receita
        r["itens"] += 1
        r["clientes"].add(l.cliente)

    rodadas_vendidas = len(por_rodada)
    ticket_medio = (receita_total / rodadas_vendidas) if rodadas_vendidas else 0
    margem = receita_total - receita_seria_partida
    # Positivo = fornecedor vendeu POR CIMA do preco de partida (raro).
    # Negativo = fornecedor abriu margem pra vencer (cenario comum).
    margem_pct = (margem / receita_seria_partida * 100) if receita_seria_partida > 0 else 0

    top_clientes = sorted(
        receita_por_cliente.values(), key=lambda c: c["gasto"], reverse=True
    )[:10]
    top_clientes = [
        (c["nome"], c["gasto"], c["itens"],
         round(c["gasto"] / receita_total * 100, 1) if receita_total else 0)
        for c in top_clientes
    ]

    top_produtos = sorted(
        por_produto.values(), key=lambda p: p["receita"], reverse=True,
    )[:10]
    top_produtos = [
        (p["nome"], p["unidade"], p["qtd"], p["receita"],
         round(p["receita"] / p["qtd"], 2) if p["qtd"] else 0)
        for p in top_produtos
    ]

    por_rodada_list = sorted(
        por_rodada.values(), key=lambda r: r["data"] or 0, reverse=True,
    )
    for r in por_rodada_list:
        r["clientes"] = ", ".join(sorted(r["clientes"]))

    return {
        "kpis": {
            "receita_total": round(receita_total, 2),
            "ticket_medio": round(ticket_medio, 2),
            "rodadas_vendidas": rodadas_vendidas,
            "margem_vs_partida": round(margem, 2),
            "margem_vs_partida_pct": round(margem_pct, 1),
        },
        "top_clientes": top_clientes,
        "top_produtos": top_produtos,
        "por_rodada": por_rodada_list,
    }
