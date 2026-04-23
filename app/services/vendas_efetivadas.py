"""Query canonica de vendas efetivadas — fonte unica de CMV e P&L.

Regra de inclusao (mesma dos 2 servicos):
- Cotacao.selecionada=True pro produto+rodada+fornecedor
- ParticipacaoRodada.aceite_proposta=True (lanchonete aceitou a proposta)

Garantir fonte unica evita o CMV/P&L divergirem com o tempo.
"""
from app import db
from app.models import (
    Rodada, Produto, Lanchonete, Fornecedor, ItemPedido, Cotacao,
    RodadaProduto, ParticipacaoRodada,
)


def linhas_efetivadas(lanchonete_id: int = None, fornecedor_id: int = None):
    """Retorna linhas (row-like) de itens efetivamente comprados/vendidos.

    Filtros opcionais:
        lanchonete_id: limita pro CMV de 1 lanchonete
        fornecedor_id: limita pro P&L de 1 fornecedor (via Cotacao.fornecedor_id)

    Schema de cada linha (acesso por atributo):
        rodada_id, rodada_nome, data, produto_id, produto_nome, categoria,
        unidade, lanchonete_id, cliente, fornecedor_id, fornecedor,
        quantidade, preco_final, preco_partida
    """
    q = (
        db.session.query(
            Rodada.id.label("rodada_id"),
            Rodada.nome.label("rodada_nome"),
            Rodada.data_abertura.label("data"),
            Produto.id.label("produto_id"),
            Produto.nome.label("produto_nome"),
            Produto.categoria.label("categoria"),
            Produto.unidade.label("unidade"),
            Lanchonete.id.label("lanchonete_id"),
            Lanchonete.nome_fantasia.label("cliente"),
            Fornecedor.id.label("fornecedor_id"),
            Fornecedor.razao_social.label("fornecedor"),
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
              (Cotacao.selecionada.is_(True)))
        .outerjoin(Fornecedor, Fornecedor.id == Cotacao.fornecedor_id)
        .outerjoin(RodadaProduto,
                   (RodadaProduto.rodada_id == ItemPedido.rodada_id) &
                   (RodadaProduto.produto_id == ItemPedido.produto_id))
        .filter(ParticipacaoRodada.aceite_proposta.is_(True))
    )
    if lanchonete_id is not None:
        q = q.filter(ItemPedido.lanchonete_id == lanchonete_id)
    if fornecedor_id is not None:
        q = q.filter(Cotacao.fornecedor_id == fornecedor_id)

    return q.order_by(Rodada.data_abertura.desc(), Produto.nome).all()
