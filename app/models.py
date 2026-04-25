from datetime import datetime, timezone
from flask_login import UserMixin
from sqlalchemy import Numeric, UniqueConstraint, Index, CheckConstraint
from app import db, login_manager


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(Usuario, int(user_id))


class Usuario(UserMixin, db.Model):
    """Usuário do sistema — admin, lanchonete ou fornecedor."""
    __tablename__ = "usuarios"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    senha_hash = db.Column(db.String(256), nullable=False)
    nome_responsavel = db.Column(db.String(100), nullable=False)
    telefone = db.Column(db.String(20))
    tipo = db.Column(db.String(20), default="lanchonete", index=True)  # admin, lanchonete, fornecedor
    ativo = db.Column(db.Boolean, default=True, nullable=False, index=True)
    criado_em = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    # Marcador pra invalidar tokens de reset + sessoes ao trocar senha.
    # Cada redefinir_senha / perfil com troca de senha atualiza esse campo.
    senha_atualizada_em = db.Column(db.DateTime(timezone=True), nullable=True)

    # Chat ID do Telegram. Unique+index pra webhook futuro achar user dono
    # rapido. BigInteger suporta IDs negativos (grupos) e positivos (1:1).
    telegram_chat_id = db.Column(db.BigInteger, nullable=True, index=True, unique=True)

    # lazy='joined' evita query extra a cada current_user.lanchonete/fornecedor
    # (acontece em quase todo request logado pelo decorator + templates).
    lanchonete = db.relationship(
        "Lanchonete", backref="responsavel", uselist=False,
        foreign_keys="Lanchonete.usuario_id", lazy="joined",
    )
    fornecedor = db.relationship(
        "Fornecedor", backref="responsavel", uselist=False,
        foreign_keys="Fornecedor.usuario_id", lazy="joined",
    )

    @property
    def is_admin(self):
        return self.tipo == "admin"

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
    ativa = db.Column(db.Boolean, default=True, index=True)
    criado_em = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

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
    criado_em = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class Rodada(db.Model):
    """Rodada de compras — período onde pedidos são agregados."""
    __tablename__ = "rodadas"

    # Constantes de status (usar em filtros/comparacoes em vez de strings cruas).
    # Fluxo atual: PREPARANDO -> AGUARDANDO_COTACAO -> ABERTA -> EM_NEGOCIACAO -> FINALIZADA.
    # FECHADA e COTANDO sao status legados de fluxo antigo (mantidos pra
    # compat com rodadas historicas).
    STATUS_PREPARANDO         = "preparando"
    STATUS_AGUARDANDO_COTACAO = "aguardando_cotacao"
    STATUS_ABERTA             = "aberta"
    STATUS_EM_NEGOCIACAO      = "em_negociacao"
    STATUS_FECHADA            = "fechada"   # legado
    STATUS_COTANDO            = "cotando"   # legado
    STATUS_FINALIZADA         = "finalizada"
    STATUS_CANCELADA          = "cancelada"

    STATUS_VALIDOS = (
        STATUS_PREPARANDO, STATUS_AGUARDANDO_COTACAO, STATUS_ABERTA,
        STATUS_EM_NEGOCIACAO, STATUS_FECHADA, STATUS_COTANDO,
        STATUS_FINALIZADA, STATUS_CANCELADA,
    )

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    data_abertura = db.Column(db.DateTime(timezone=True), nullable=False)
    data_fechamento = db.Column(db.DateTime(timezone=True), nullable=False)
    status = db.Column(db.String(20), default=STATUS_ABERTA, index=True)
    criado_em = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Deadlines por fase do fluxo (opcional — se null, usa data_fechamento como padrao)
    deadline_pedido       = db.Column(db.DateTime(timezone=True))  # ate quando lanchonete envia pedido
    deadline_cotacao      = db.Column(db.DateTime(timezone=True))  # ate quando fornecedor envia cotacao
    deadline_aceite       = db.Column(db.DateTime(timezone=True))  # ate quando lanchonete aceita proposta final
    deadline_pagamento    = db.Column(db.DateTime(timezone=True))  # ate quando lanchonete paga
    deadline_entrega      = db.Column(db.DateTime(timezone=True))  # ate quando fornecedor entrega
    deadline_confirmacao  = db.Column(db.DateTime(timezone=True))  # ate quando lanchonete confirma recebimento

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
    criado_em = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    produto = db.relationship("Produto")

    __table_args__ = (
        Index("ix_itens_pedido_rodada_lanchonete", "rodada_id", "lanchonete_id"),
        CheckConstraint("quantidade > 0", name="ck_item_pedido_qtd_positiva"),
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
    ativo = db.Column(db.Boolean, default=True, index=True)
    # Opt-in LGPD: so aparece no marketplace publico se explicitamente True.
    # Default False pro comportamento novo ser "conservador" (fornecedor escolhe aparecer).
    aparece_no_marketplace = db.Column(db.Boolean, default=False, nullable=False)
    criado_em = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

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
    validade = db.Column(db.DateTime(timezone=True))
    selecionada = db.Column(db.Boolean, default=False, index=True)
    criado_em = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    produto = db.relationship("Produto")

    __table_args__ = (
        UniqueConstraint("rodada_id", "fornecedor_id", "produto_id",
                         name="uq_cotacao_rodada_fornecedor_produto"),
        # Unique partial: no maximo 1 vencedora por (rodada, produto).
        # Postgres e SQLite suportam partial index via WHERE.
        db.Index(
            "ix_cotacao_vencedora_unica",
            "rodada_id", "produto_id",
            unique=True,
            postgresql_where=db.text("selecionada IS TRUE"),
            sqlite_where=db.text("selecionada IS TRUE"),
        ),
        # Query mais quente do fornecedor: filter_by(rodada_id=X, fornecedor_id=Y).
        db.Index("ix_cotacao_rodada_fornecedor", "rodada_id", "fornecedor_id"),
        # Ranking de menor preco por produto na rodada.
        db.Index("ix_cotacao_rodada_produto", "rodada_id", "produto_id"),
        CheckConstraint("preco_unitario > 0", name="ck_cotacao_preco_positivo"),
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

    # Fase: submissao do pedido (moderacao do admin)
    # rascunho: pedido_enviado_em = NULL  (lanchonete ainda editando)
    # enviado: pedido_enviado_em != NULL, aprovado_em = NULL, devolvido_em = NULL, reprovado_em = NULL
    # aprovado: pedido_aprovado_em != NULL  (admin liberou pro pool da rodada)
    # devolvido: pedido_devolvido_em != NULL  (lanchonete precisa ajustar e reenviar)
    # reprovado: pedido_reprovado_em != NULL  (bloqueado)
    pedido_enviado_em       = db.Column(db.DateTime(timezone=True))
    pedido_aprovado_em      = db.Column(db.DateTime(timezone=True))
    pedido_aprovado_por_id  = db.Column(db.Integer, db.ForeignKey("usuarios.id"), index=True)
    pedido_devolvido_em     = db.Column(db.DateTime(timezone=True))
    pedido_motivo_devolucao = db.Column(db.String(500))
    pedido_reprovado_em     = db.Column(db.DateTime(timezone=True))

    # Fase: aceite da proposta consolidada
    # null = pendente | True = aceitou | False = recusou
    aceite_proposta    = db.Column(db.Boolean, index=True)
    aceite_em          = db.Column(db.DateTime(timezone=True))

    # Fase: comprovante de pagamento (chave opaca de storage — caminho no disco/S3)
    comprovante_key    = db.Column(db.String(255))
    comprovante_em     = db.Column(db.DateTime(timezone=True))

    # Fase: fornecedor confirma recebimento do pagamento
    pagamento_confirmado_em      = db.Column(db.DateTime(timezone=True))
    pagamento_confirmado_por_id  = db.Column(db.Integer, db.ForeignKey("usuarios.id"), index=True)

    # Fase: fornecedor informa entrega
    entrega_informada_em   = db.Column(db.DateTime(timezone=True))
    entrega_informada_por_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), index=True)
    entrega_data           = db.Column(db.Date)  # data real da entrega

    # Fase: cliente confirma recebimento
    # null = pendente | True = recebeu OK | False = problema
    recebimento_ok           = db.Column(db.Boolean)
    recebimento_em           = db.Column(db.DateTime(timezone=True))
    recebimento_observacao   = db.Column(db.String(500))

    # Avaliacao geral da rodada (opcao D: 1-5 estrelas; se <=3 cliente detalha por fornecedor)
    avaliacao_geral   = db.Column(db.Integer)  # 1-5
    avaliacao_em      = db.Column(db.DateTime(timezone=True))

    criado_em = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Relationships para queries
    rodada      = db.relationship("Rodada", backref="participacoes")
    lanchonete  = db.relationship("Lanchonete", backref="participacoes")

    __table_args__ = (
        UniqueConstraint("rodada_id", "lanchonete_id",
                         name="uq_participacao_rodada_lanchonete"),
        # Fila de moderacao: pedidos enviados ainda sem decisao do admin.
        db.Index(
            "ix_participacao_pedido_pendente",
            "rodada_id",
            postgresql_where=db.text(
                "pedido_enviado_em IS NOT NULL "
                "AND pedido_aprovado_em IS NULL "
                "AND pedido_reprovado_em IS NULL"
            ),
            sqlite_where=db.text(
                "pedido_enviado_em IS NOT NULL "
                "AND pedido_aprovado_em IS NULL "
                "AND pedido_reprovado_em IS NULL"
            ),
        ),
        CheckConstraint(
            "avaliacao_geral IS NULL OR avaliacao_geral BETWEEN 1 AND 5",
            name="ck_participacao_avaliacao_1a5",
        ),
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
    criado_em  = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    rodada      = db.relationship("Rodada")
    lanchonete  = db.relationship("Lanchonete")
    fornecedor  = db.relationship("Fornecedor")

    __table_args__ = (
        UniqueConstraint("rodada_id", "lanchonete_id", "fornecedor_id",
                         name="uq_avaliacao_rodada_lanchonete_fornecedor"),
        CheckConstraint("estrelas BETWEEN 1 AND 5", name="ck_avaliacao_estrelas_1a5"),
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
    ator_id       = db.Column(db.Integer, db.ForeignKey("usuarios.id"), index=True)  # quem fez (null = sistema)
    tipo          = db.Column(db.String(40), nullable=False)
    descricao     = db.Column(db.String(500))
    criado_em     = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)

    rodada     = db.relationship("Rodada", backref="eventos")
    lanchonete = db.relationship("Lanchonete")
    ator       = db.relationship("Usuario")

    __table_args__ = (
        # Timeline ordenada por rodada: evita sort externo em detalhes de rodada.
        db.Index("ix_evento_rodada_criado", "rodada_id", "criado_em"),
    )


# ---------- Fase A.1: catalogo da rodada (produtos selecionados + preco de partida) ----------


class RodadaProduto(db.Model):
    """Produto que faz parte do catálogo de uma rodada específica.

    Admin sobe a lista de produtos (preco_partida = null).
    Fornecedor preenche preco_partida.
    Fornecedor pode sugerir produto novo (adicionado_por_fornecedor_id preenchido +
    aprovado = None). Admin aprova (aprovado=True) ou recusa (aprovado=False).
    Se todos os produtos estão aprovados (ou nao ha produto sugerido), a rodada é
    liberada para as lanchonetes marcarem quantidades.
    """
    __tablename__ = "rodada_produtos"

    id = db.Column(db.Integer, primary_key=True)
    rodada_id  = db.Column(db.Integer, db.ForeignKey("rodadas.id"), nullable=False, index=True)
    produto_id = db.Column(db.Integer, db.ForeignKey("produtos.id"), nullable=False, index=True)

    # Preco de partida (fornecedor preenche depois que admin monta o catalogo)
    preco_partida = db.Column(Numeric(12, 2))

    # Quem sugeriu: null = admin (durante montagem); fornecedor_id = sugerido durante cotacao
    adicionado_por_fornecedor_id = db.Column(db.Integer, db.ForeignKey("fornecedores.id"), index=True)

    # Aprovacao: None = aprovado automaticamente (admin adicionou); True = admin aprovou; False = admin recusou
    aprovado = db.Column(db.Boolean, default=None)
    criado_em = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    produto    = db.relationship("Produto")
    rodada     = db.relationship("Rodada", backref="catalogo")
    fornecedor_sugeriu = db.relationship("Fornecedor")

    __table_args__ = (
        UniqueConstraint("rodada_id", "produto_id",
                         name="uq_rodada_produto"),
    )


# ---------- Submissao da cotacao final (fornecedor -> admin aprova/devolve) ----------
class SubmissaoCotacao(db.Model):
    """Agrega os precos finais enviados por um fornecedor numa rodada.

    Fluxo:
    1. Fornecedor preenche precos finais em Cotacao (existente)
    2. Fornecedor clica 'Enviar pra aprovacao' -> enviada_em=now
    3. Admin aprova (aprovada_em=now) OU devolve (devolvida_em=now)
    4. Se devolvida: admin e fornecedor trocam notas (NotaNegociacao) ate reenviar
    5. Quando aprovada, precos ficam visiveis pras lanchonetes
    """
    __tablename__ = "submissoes_cotacao"

    id = db.Column(db.Integer, primary_key=True)
    rodada_id     = db.Column(db.Integer, db.ForeignKey("rodadas.id"), nullable=False, index=True)
    fornecedor_id = db.Column(db.Integer, db.ForeignKey("fornecedores.id"), nullable=False, index=True)

    enviada_em         = db.Column(db.DateTime(timezone=True))
    aprovada_em        = db.Column(db.DateTime(timezone=True))
    aprovada_por_id    = db.Column(db.Integer, db.ForeignKey("usuarios.id", name="fk_submissao_aprovada_por"), index=True)
    devolvida_em       = db.Column(db.DateTime(timezone=True))

    criado_em = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    rodada     = db.relationship("Rodada")
    fornecedor = db.relationship("Fornecedor")

    __table_args__ = (
        UniqueConstraint("rodada_id", "fornecedor_id",
                         name="uq_submissao_rodada_fornecedor"),
    )


class NotaNegociacao(db.Model):
    """Anotacoes append-only entre admin e fornecedor numa submissao de cotacao.

    Quando admin devolve a cotacao, ambos podem adicionar notas. Cada nota
    tem autor (admin ou fornecedor) + texto + timestamp, exibidas em ordem
    cronologica como historico da negociacao.
    """
    __tablename__ = "notas_negociacao"

    AUTOR_ADMIN      = "admin"
    AUTOR_FORNECEDOR = "fornecedor"

    id = db.Column(db.Integer, primary_key=True)
    submissao_id = db.Column(db.Integer,
        db.ForeignKey("submissoes_cotacao.id", name="fk_nota_submissao"),
        nullable=False, index=True)
    autor_tipo       = db.Column(db.String(20), nullable=False)  # admin | fornecedor
    autor_usuario_id = db.Column(db.Integer,
        db.ForeignKey("usuarios.id", name="fk_nota_autor"),
        nullable=False, index=True)
    texto     = db.Column(db.String(1000), nullable=False)
    criado_em = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)

    submissao    = db.relationship("SubmissaoCotacao", backref="notas")
    autor_usuario = db.relationship("Usuario")