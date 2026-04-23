"""Calculo do CMV (Custo da Mercadoria Vendida) da lanchonete logada.

Agrega gastos efetivos em compras ja aceitas, economia vs. preco de partida,
tickets por rodada, top categorias/produtos. Usado na tela /minhas-rodadas/cmv.

Regra: so conta linhas onde a lanchonete ACEITOU a proposta (aceite_proposta=True)
e onde existe Cotacao selecionada (selecionada=True) pro produto naquela rodada.
"""
from collections import defaultdict
from app.services.vendas_efetivadas import linhas_efetivadas


def calcular_cmv(lanchonete_id: int) -> dict:
    """Retorna dict com KPIs, top categorias, top produtos e linhas por rodada.

    Esquema:
    {
        "kpis": {"gasto_total", "economia_total", "economia_pct",
                 "ticket_medio", "rodadas_compradas"},
        "top_categorias": [(nome, gasto_rs, pct)],
        "top_produtos":   [(nome, unidade, qtd_total, gasto_rs, preco_medio)],
        "por_rodada":     [{rodada_id, rodada_nome, data, gasto, economia, itens, fornecedor}],
    }
    """
    linhas = linhas_efetivadas(lanchonete_id=lanchonete_id)

    # 2. Agrega KPIs + top categorias + top produtos + por rodada
    gasto_total = 0.0
    economia_total = 0.0
    gasto_por_cat = defaultdict(float)
    gasto_por_produto = defaultdict(lambda: {"nome": "", "unidade": "",
                                               "qtd": 0.0, "gasto": 0.0})
    por_rodada = {}

    for l in linhas:
        qtd = float(l.quantidade or 0)
        final = float(l.preco_final or 0)
        partida = float(l.preco_partida) if l.preco_partida else final
        gasto = qtd * final
        econ = qtd * max(partida - final, 0)

        gasto_total += gasto
        economia_total += econ
        gasto_por_cat[l.categoria] += gasto

        p = gasto_por_produto[l.produto_id]
        p["nome"] = l.produto_nome
        p["unidade"] = l.unidade
        p["qtd"] += qtd
        p["gasto"] += gasto

        rod = por_rodada.setdefault(l.rodada_id, {
            "rodada_id": l.rodada_id,
            "rodada_nome": l.rodada_nome,
            "data": l.data,
            "gasto": 0.0,
            "economia": 0.0,
            "itens": 0,
            "fornecedores": set(),
        })
        rod["gasto"] += gasto
        rod["economia"] += econ
        rod["itens"] += 1
        if l.fornecedor:
            rod["fornecedores"].add(l.fornecedor)

    rodadas_compradas = len(por_rodada)
    ticket_medio = (gasto_total / rodadas_compradas) if rodadas_compradas else 0
    economia_pct = (economia_total / (gasto_total + economia_total) * 100) \
        if (gasto_total + economia_total) > 0 else 0

    # Top 5 categorias
    top_categorias = sorted(gasto_por_cat.items(), key=lambda x: x[1], reverse=True)[:5]
    top_categorias = [
        (nome, gasto, round(gasto / gasto_total * 100, 1) if gasto_total else 0)
        for nome, gasto in top_categorias
    ]

    # Top 10 produtos
    top_produtos = sorted(
        gasto_por_produto.values(), key=lambda x: x["gasto"], reverse=True
    )[:10]
    top_produtos = [
        (p["nome"], p["unidade"], p["qtd"], p["gasto"],
         round(p["gasto"] / p["qtd"], 2) if p["qtd"] else 0)
        for p in top_produtos
    ]

    # Por rodada (ordenado por data desc)
    por_rodada_list = sorted(
        por_rodada.values(), key=lambda r: r["data"] or 0, reverse=True,
    )
    for r in por_rodada_list:
        r["fornecedores"] = ", ".join(sorted(r["fornecedores"]))

    return {
        "kpis": {
            "gasto_total": round(gasto_total, 2),
            "economia_total": round(economia_total, 2),
            "economia_pct": round(economia_pct, 1),
            "ticket_medio": round(ticket_medio, 2),
            "rodadas_compradas": rodadas_compradas,
        },
        "top_categorias": top_categorias,
        "top_produtos": top_produtos,
        "por_rodada": por_rodada_list,
    }
