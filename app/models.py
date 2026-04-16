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
    categoria = db.Column(db.String(50), nullable=False)
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
    status = db.Column(db.String(20), default="aberta")  # aberta, fechada, cotando, finalizada
    criado_em = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

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