from datetime import datetime, timezone
from flask_login import UserMixin
from sqlalchemy import Numeric, UniqueConstraint, Index
from app import db, login_manager


@login_manager.user_loader
def load_user(user_id):
    return Usuario.query.get(int(user_id))


class Usuario(UserMixin, db.Model):
    """Usuário do sistema — admin, lanchonete ou fornecedor."""
    __tablename__ = "usuarios"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    senha_hash = db.Column(db.String(256), nullable=False)
    nome_responsavel = db.Column(db.String(100), nullable=False)
    telefone = db.Column(db.String(20))
    tipo = db.Column(db.String(20), default="lanchonete")  # admin, lanchonete, fornecedor
    is_admin = db.Column(db.Boolean, default=False)
    criado_em = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    lanchonete = db.relationship("Lanchonete", backref="responsavel", uselist=False)
    fornecedor = db.relationship("Fornecedor", backref="responsavel", uselist=False)

    @property
    def is_fornecedor(self):
        return self.tipo == "fornecedor"

    @property
    def is_lanchonete(self):
        return self.tipo == "lanchonete"


class Lanchonete(db.Model):
    """Hamburguerias e lanchonetes cadastradas."""
    __tablename__ = "lanchonetes"

    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    nome_fantasia = db.Column(db.String(100), nullable=False)
    cnpj = db.Column(db.String(18), unique=True)
    endereco = db.Column(db.String(200))
    bairro = db.Column(db.String(80))
    cidade = db.Column(db.String(80), default="Londrina")
    ativa = db.Column(db.Boolean, default=True)
    criado_em = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    pedidos = db.relationship("ItemPedido", backref="lanchonete")


class Produto(db.Model):
    """Catálogo de insumos padronizados."""
    __tablename__ = "produtos"

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    descricao = db.Column(db.String(300))
    categoria = db.Column(db.String(50), nullable=False, index=True)
    subcategoria = db.Column(db.String(50), index=True)
    unidade = db.Column(db.String(20), nullable=False)
    ativo = db.Column(db.Boolean, default=True)
    criado_em = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))


class Rodada(db.Model):
    """Rodada de compras — período onde pedidos são agregados."""
    __tablename__ = "rodadas"

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    data_abertura = db.Column(db.DateTime, nullable=False)
    data_fechamento = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String(20), default="aberta")  # aberta, fechada, cotando, finalizada, cancelada
    criado_em = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    # Deadlines por fase do fluxo (opcional — se null, usa data_fechamento como padrao)
    deadline_pedido       = db.Column(db.DateTime)  # ate quando lanchonete envia pedido
    deadline_cotacao      = db.Column(db.DateTime)  # ate quando fornecedor envia cotacao
    deadline_aceite       = db.Column(db.DateTime)  # ate quando lanchonete aceita proposta final
    deadline_pagamento    = db.Column(db.DateTime)  # ate quando lanchonete paga
    deadline_entrega      = db.Column(db.DateTime)  # ate quando fornecedor entrega
    deadline_confirmacao  = db.Column(db.DateTime)  # ate quando lanchonete confirma recebimento

    itens = db.relationship("ItemPedido", backref="rodada")
    cotacoes = db.relationship("Cotacao", backref="rodada")


class ItemPedido(db.Model):
    """Pedido de um produto por uma lanchonete numa rodada."""
    __tablename__ = "itens_pedido"

    id = db.Column(db.Integer, primary_key=True)
    rodada_id = db.Column(db.Integer, db.ForeignKey("rodadas.id"), nullable=False, index=True)
    lanchonete_id = db.Column(db.Integer, db.ForeignKey("lanchonetes.id"), nullable=False, index=True)
    produto_id = db.Column(db.Integer, db.ForeignKey("produtos.id"), nullable=False, index=True)
    # Numeric(10,3) suporta ate 3 casas (suficiente para kg/litro fracionario)
    quantidade = db.Column(Numeric(10, 3), nullable=False)
    observacao = db.Column(db.String(200))
    criado_em = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    produto = db.relationship("Produto")

    __table_args__ = (
        Index("ix_itens_pedido_rodada_lanchonete", "rodada_id", "lanchonete_id"),
    )


class Fornecedor(db.Model):
    """Fornecedores que enviam cotações."""
    __tablename__ = "fornecedores"

    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=True)
    razao_social = db.Column(db.String(150), nullable=False)
    nome_contato = db.Column(db.String(100))
    telefone = db.Column(db.String(20))
    email = db.Column(db.String(120))
    cidade = db.Column(db.String(80))
    ativo = db.Column(db.Boolean, default=True)
    criado_em = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    # Dados para pagamento (lanchonete paga por fora do sistema)
    chave_pix = db.Column(db.String(150))     # CNPJ/email/telefone/aleatoria
    banco = db.Column(db.String(80))
    agencia = db.Column(db.String(20))
    conta = db.Column(db.String(30))

    cotacoes = db.relationship("Cotacao", backref="fornecedor")


class Cotacao(db.Model):
    """Preço de um fornecedor para um produto numa rodada."""
    __tablename__ = "cotacoes"

    id = db.Column(db.Integer, primary_key=True)
    rodada_id = db.Column(db.Integer, db.ForeignKey("rodadas.id"), nullable=False, index=True)
    fornecedor_id = db.Column(db.Integer, db.ForeignKey("fornecedores.id"), nullable=False, index=True)
    produto_id = db.Column(db.Integer, db.ForeignKey("produtos.id"), nullable=False, index=True)
    # Numeric(12,2) suporta ate ~10 bilhoes; perfeito para precos em BRL
    preco_unitario = db.Column(Numeric(12, 2), nullable=False)
    quantidade_minima = db.Column(Numeric(10, 3))
    validade = db.Column(db.DateTime)
    selecionada = db.Column(db.Boolean, default=False)
    criado_em = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    produto = db.relationship("Produto")

    __table_args__ = (
        # Cada fornecedor envia 1 cotacao por (rodada, produto). Evita duplicatas.
        UniqueConstraint("rodada_id", "fornecedor_id", "produto_id",
                         name="uq_cotacao_rodada_fornecedor_produto"),
    )


# ---------- Fase 2: controle de fluxo por lanchonete ----------


class ParticipacaoRodada(db.Model):
    """Agregador do fluxo de uma lanchonete dentro de uma rodada.

    Uma linha por (rodada, lanchonete). Concentra o progresso nas fases:
    aceite da proposta -> comprovante -> confirmacao de pagamento -> entrega ->
    recebimento -> avaliacao. Campos ficam null enquanto nao acontecem.
    """
    __tablename__ = "participacoes_rodada"

    id = db.Column(db.Integer, primary_key=True)
    rodada_id     = db.Column(db.Integer, db.ForeignKey("rodadas.id"), nullable=False, index=True)
    lanchonete_id = db.Column(db.Integer, db.ForeignKey("lanchonetes.id"), nullable=False, index=True)

    # Fase: aceite da proposta consolidada
    # null = pendente | True = aceitou | False = recusou
    aceite_proposta    = db.Column(db.Boolean)
    aceite_em          = db.Column(db.DateTime)

    # Fase: comprovante de pagamento (chave opaca de storage — caminho no disco/S3)
    comprovante_key    = db.Column(db.String(255))
    comprovante_em     = db.Column(db.DateTime)

    # Fase: fornecedor confirma recebimento do pagamento
    pagamento_confirmado_em      = db.Column(db.DateTime)
    pagamento_confirmado_por_id  = db.Column(db.Integer, db.ForeignKey("usuarios.id"))

    # Fase: fornecedor informa entrega
    entrega_informada_em   = db.Column(db.DateTime)
    entrega_informada_por_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"))
    entrega_data           = db.Column(db.Date)  # data real da entrega

    # Fase: cliente confirma recebimento
    # null = pendente | True = recebeu OK | False = problema
    recebimento_ok           = db.Column(db.Boolean)
    recebimento_em           = db.Column(db.DateTime)
    recebimento_observacao   = db.Column(db.String(500))

    # Avaliacao geral da rodada (opcao D: 1-5 estrelas; se <=3 cliente detalha por fornecedor)
    avaliacao_geral   = db.Column(db.Integer)  # 1-5
    avaliacao_em      = db.Column(db.DateTime)

    criado_em = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships para queries
    rodada      = db.relationship("Rodada", backref="participacoes")
    lanchonete  = db.relationship("Lanchonete", backref="participacoes")

    __table_args__ = (
        UniqueConstraint("rodada_id", "lanchonete_id",
                         name="uq_participacao_rodada_lanchonete"),
    )


class AvaliacaoRodada(db.Model):
    """Avaliacao por fornecedor dentro de uma rodada (opcao D — so preenche se nota geral <= 3).

    Uma linha por (rodada, lanchonete, fornecedor). Se a lanchonete deu nota geral >= 4,
    o sistema cria AvaliacaoRodada com a mesma nota pra todos os fornecedores da rodada.
    Se nota <= 3, a lanchonete detalha individualmente aqui.
    """
    __tablename__ = "avaliacoes_rodada"

    id = db.Column(db.Integer, primary_key=True)
    rodada_id      = db.Column(db.Integer, db.ForeignKey("rodadas.id"), nullable=False, index=True)
    lanchonete_id  = db.Column(db.Integer, db.ForeignKey("lanchonetes.id"), nullable=False, index=True)
    fornecedor_id  = db.Column(db.Integer, db.ForeignKey("fornecedores.id"), nullable=False, index=True)

    estrelas   = db.Column(db.Integer, nullable=False)  # 1-5
    comentario = db.Column(db.String(500))
    criado_em  = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    rodada      = db.relationship("Rodada")
    lanchonete  = db.relationship("Lanchonete")
    fornecedor  = db.relationship("Fornecedor")

    __table_args__ = (
        UniqueConstraint("rodada_id", "lanchonete_id", "fornecedor_id",
                         name="uq_avaliacao_rodada_lanchonete_fornecedor"),
    )


class EventoRodada(db.Model):
    """Log imutavel de eventos para timeline e auditoria.

    Cada transicao de estado no fluxo de uma rodada (por lanchonete ou global)
    gera uma linha aqui. Usado para renderizar a timeline e investigar
    incidentes em producao (quem fez o que, quando).
    """
    __tablename__ = "eventos_rodada"

    # Tipos conhecidos de evento. Usar constantes reduz typos no codigo chamador.
    TIPO_PEDIDO_ENVIADO          = "pedido_enviado"
    TIPO_RODADA_FECHADA          = "rodada_fechada"
    TIPO_COTACAO_ENVIADA         = "cotacao_enviada"
    TIPO_PROPOSTA_CONSOLIDADA    = "proposta_consolidada"
    TIPO_PROPOSTA_ACEITA         = "proposta_aceita"
    TIPO_PROPOSTA_RECUSADA       = "proposta_recusada"
    TIPO_COMPROVANTE_ENVIADO     = "comprovante_enviado"
    TIPO_PAGAMENTO_CONFIRMADO    = "pagamento_confirmado"
    TIPO_ENTREGA_INFORMADA       = "entrega_informada"
    TIPO_RECEBIMENTO_CONFIRMADO  = "recebimento_confirmado"
    TIPO_RECEBIMENTO_PROBLEMA    = "recebimento_problema"
    TIPO_AVALIACAO_ENVIADA       = "avaliacao_enviada"
    TIPO_RODADA_FINALIZADA       = "rodada_finalizada"
    TIPO_RODADA_CANCELADA        = "rodada_cancelada"
    TIPO_DEADLINE_VENCIDO        = "deadline_vencido"

    id = db.Column(db.Integer, primary_key=True)
    rodada_id     = db.Column(db.Integer, db.ForeignKey("rodadas.id"), nullable=False, index=True)
    lanchonete_id = db.Column(db.Integer, db.ForeignKey("lanchonetes.id"), index=True)  # null = evento global
    ator_id       = db.Column(db.Integer, db.ForeignKey("usuarios.id"))  # quem fez (null = sistema)
    tipo          = db.Column(db.String(40), nullable=False)
    descricao     = db.Column(db.String(500))
    criado_em     = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)

    rodada     = db.relationship("Rodada", backref="eventos")
    lanchonete = db.relationship("Lanchonete")
    ator       = db.relationship("Usuario")