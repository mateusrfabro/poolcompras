"""Calculo do P&L (receita/margem) do fornecedor logado.

Espelha cmv_lanchonete.py, mas do lado oposto da relacao: soma vendas
efetivas (cotacoes selecionadas × volumes aceitos) agrupadas por cliente,
produto e rodada.

Regra: so conta linhas onde (a) Cotacao.selecionada=True e (b) a lanchonete
dona do ItemPedido aceitou a proposta (aceite_proposta=True). Isso garante
paridade com o que aparece no CMV da lanchonete — o somatorio de CMV de
todas lanchonetes = soma dos P&L de todos fornecedores.

Aritmetica monetaria em Decimal (R$ tem 2 casas — float acumula drift).
Conversao pra float so no payload final (o filtro |brl no template aceita
qualquer numero).
"""
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP

from app.services.vendas_efetivadas import linhas_efetivadas


_ZERO = Decimal("0")
_CENT = Decimal("0.01")


def _to_dec(v) -> Decimal:
    if v is None:
        return _ZERO
    if isinstance(v, Decimal):
        return v
    return Decimal(str(v))


def _q2(v: Decimal) -> float:
    """Quantize pra 2 casas e devolve float (payload pro template)."""
    return float(v.quantize(_CENT, rounding=ROUND_HALF_UP))


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
    linhas = linhas_efetivadas(fornecedor_id=fornecedor_id)

    receita_total = _ZERO
    receita_seria_partida = _ZERO
    receita_por_cliente = defaultdict(lambda: {"gasto": _ZERO, "itens": 0})
    por_produto = defaultdict(lambda: {"nome": "", "unidade": "",
                                         "qtd": _ZERO, "receita": _ZERO})
    por_rodada = {}

    for l in linhas:
        qtd = _to_dec(l.quantidade)
        final = _to_dec(l.preco_final)
        partida = _to_dec(l.preco_partida) if l.preco_partida else final
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
            "receita": _ZERO,
            "itens": 0,
            "clientes": set(),
        })
        r["receita"] += receita
        r["itens"] += 1
        r["clientes"].add(l.cliente)

    rodadas_vendidas = len(por_rodada)
    ticket_medio = (receita_total / rodadas_vendidas) if rodadas_vendidas else _ZERO
    margem = receita_total - receita_seria_partida
    # Positivo = fornecedor vendeu POR CIMA do preco de partida (raro).
    # Negativo = fornecedor abriu margem pra vencer (cenario comum).
    if receita_seria_partida > _ZERO:
        margem_pct = float((margem / receita_seria_partida * Decimal("100"))
                           .quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))
    else:
        margem_pct = 0.0

    top_clientes_raw = sorted(
        receita_por_cliente.values(), key=lambda c: c["gasto"], reverse=True
    )[:10]
    top_clientes = [
        (
            c["nome"],
            _q2(c["gasto"]),
            c["itens"],
            float((c["gasto"] / receita_total * Decimal("100"))
                  .quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))
            if receita_total > _ZERO else 0.0,
        )
        for c in top_clientes_raw
    ]

    top_produtos_raw = sorted(
        por_produto.values(), key=lambda p: p["receita"], reverse=True,
    )[:10]
    top_produtos = [
        (
            p["nome"],
            p["unidade"],
            float(p["qtd"]),
            _q2(p["receita"]),
            _q2(p["receita"] / p["qtd"]) if p["qtd"] > _ZERO else 0.0,
        )
        for p in top_produtos_raw
    ]

    por_rodada_list = sorted(
        por_rodada.values(), key=lambda r: r["data"] or 0, reverse=True,
    )
    for r in por_rodada_list:
        r["clientes"] = ", ".join(sorted(r["clientes"]))
        r["receita"] = _q2(r["receita"])

    return {
        "kpis": {
            "receita_total": _q2(receita_total),
            "ticket_medio": _q2(ticket_medio),
            "rodadas_vendidas": rodadas_vendidas,
            "margem_vs_partida": _q2(margem),
            "margem_vs_partida_pct": margem_pct,
        },
        "top_clientes": top_clientes,
        "top_produtos": top_produtos,
        "por_rodada": por_rodada_list,
    }
