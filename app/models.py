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
    # LGPD: timestamp de quando o usuario aceitou Termos+Privacidade.
    # Migration a1b2c3d4e5f6 ja criou a coluna no DB; declarar aqui evita
    # drift schema/ORM (db.create_all em ambiente novo + INSERT silencioso).
    aceite_termos_em = db.Column(db.DateTime(timezone=True), nullable=True)

    # Chat ID do Telegram. Unique+index pra webhook futuro achar user dono
    # rapido. BigInteger suporta IDs negativos (grupos) e positivos (1:1).
    telegram_chat_id = db.Column(db.BigInteger, nullable=True, index=True, unique=True)

    # lazy='selectin' carrega lanchonete/fornecedor em 1 query SEPARADA pos load
    # do Usuario, em vez de LEFT JOIN duplo a cada SELECT em usuarios. Evita
    # cartesian + carga desnecessaria em rotas que nao tocam o relationship.
    # Trade-off: 2 queries por request logado em vez de 1 JOIN gordo — mais
    # barato em Postgres real.
    lanchonete = db.relationship(
        "Lanchonete", backref="responsavel", uselist=False,
        foreign_keys="Lanchonete.usuario_id", lazy="selectin",
    )
    fornecedor = db.relationship(
        "Fornecedor", backref="responsavel", uselist=False,
        foreign_keys="Fornecedor.usuario_id", lazy="selectin",
    )
    vendedor = db.relationship(
        "Vendedor", backref="responsavel", uselist=False,
        foreign_keys="Vendedor.usuario_id", lazy="selectin",
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

    @property
    def is_vendedor(self):
        return self.tipo == "vendedor"


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
    # Programa de indicacao: codigo unico que a lanchonete espalha pra
    # convidar amigas. Ex: link aggron.com.br/registro?ind=ABC123. 8 chars
    # alfanumericos sem caracteres confusos (sem 0/O/1/I/L). 32^8 = ~1.1T
    # combinacoes, colisao desprezivel. Nullable=True pra preservar legacy
    # rows; servico gera lazy no primeiro acesso ao dashboard.
    codigo_indicacao = db.Column(db.String(8), unique=True, index=True, nullable=True)

    # CRM: vendedor (SDR) responsavel pela conta. Nullable pra preservar
    # cadastros antigos sem dono. Admin pode atribuir/reatribuir manualmente.
    vendedor_id = db.Column(db.Integer, db.ForeignKey("vendedores.id"),
                            nullable=True, index=True)

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
    ativo = db.Column(db.Boolean, default=True, index=True)
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
    data_abertura = db.Column(db.DateTime(timezone=True), nullable=False, index=True)
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

    __table_args__ = (
        # Bloqueia status com typo silencioso (ex: 'aberto' em vez de 'aberta').
        # Lista bate com STATUS_VALIDOS acima. Atualizar JUNTO se adicionar status novo.
        CheckConstraint(
            "status IN ('preparando','aguardando_cotacao','aberta',"
            "'em_negociacao','fechada','cotando','finalizada','cancelada')",
            name="ck_rodada_status_valido",
        ),
    )


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

    # % de comissao que o fornecedor paga pra Aggron sobre cada venda
    # efetivada. Default 0 = legacy/sem contrato. Admin define no cadastro
    # e o valor pode ser ajustado depois (snapshot por venda fica em
    # ComissaoFornecedor — TODO v2; por agora calcula on-the-fly).
    percentual_comissao = db.Column(
        Numeric(5, 2), nullable=False, default=0,
    )

    # CRM: vendedor (SDR) responsavel. Nullable pra preservar cadastros antigos.
    vendedor_id = db.Column(db.Integer, db.ForeignKey("vendedores.id"),
                            nullable=True, index=True)

    cotacoes = db.relationship("Cotacao", backref="fornecedor")

    __table_args__ = (
        CheckConstraint(
            "percentual_comissao >= 0 AND percentual_comissao <= 100",
            name="ck_fornecedor_comissao_pct",
        ),
    )


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
        # Pendencias do fornecedor + funil de aceite filtram por
        # (rodada_id, aceite_proposta) — index composto evita seq scan.
        db.Index("ix_participacao_rodada_aceite",
                 "rodada_id", "aceite_proposta"),
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


class Indicacao(db.Model):
    """Programa de indicacao: lanchonete A indicou lanchonete B.

    Regra de recompensa (MVP): apos 3 indicadas com `ativa=True` HA mais
    de 30 dias e ainda sem recompensa aplicada, a indicadora ganha 1 mes
    gratis na proxima cobranca. Recompensa eh aplicada manualmente pela
    equipe (sistema notifica admin via Telegram).
    """
    __tablename__ = "indicacoes"

    id = db.Column(db.Integer, primary_key=True)
    indicador_lanchonete_id = db.Column(
        db.Integer, db.ForeignKey("lanchonetes.id"),
        nullable=False, index=True,
    )
    # UNIQUE: 1 lanchonete tem no maximo 1 indicador (quem chegou primeiro
    # via link). Bloqueia atacante reclassificando depois.
    indicada_lanchonete_id = db.Column(
        db.Integer, db.ForeignKey("lanchonetes.id"),
        nullable=False, unique=True,
    )
    # Snapshot do codigo usado no momento da indicacao. Caso a indicadora
    # gere codigo novo no futuro, mantem trilha do que foi usado.
    codigo_usado = db.Column(db.String(8), nullable=False)
    criado_em = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False, index=True,
    )
    # Quando essa indicacao foi "consumida" como parte de uma recompensa.
    # NULL = ainda elegivel pra computar a proxima recompensa.
    recompensa_aplicada_em = db.Column(db.DateTime(timezone=True), nullable=True)

    indicador = db.relationship(
        "Lanchonete", foreign_keys=[indicador_lanchonete_id],
        backref="indicacoes_feitas",
    )
    indicada = db.relationship(
        "Lanchonete", foreign_keys=[indicada_lanchonete_id],
    )

    __table_args__ = (
        # Bloqueia auto-indicacao no nivel do DB (defesa em profundidade —
        # service ja valida).
        CheckConstraint(
            "indicador_lanchonete_id <> indicada_lanchonete_id",
            name="ck_indicacao_nao_propria",
        ),
        # Partial index pra queries hot do dashboard de indicacoes:
        # calcular_status_recompensa, _notificar_quase_la, resgatar_recompensa.
        # Filtro recompensa_aplicada_em IS NULL casa com 100% das rows ate o
        # primeiro resgate; depois disso poda ~3 rows por resgate. ORDER BY
        # criado_em ASC do FIFO no resgate vira lookup direto.
        db.Index(
            "ix_indicacao_pendentes",
            "indicador_lanchonete_id",
            "criado_em",
            postgresql_where=db.text("recompensa_aplicada_em IS NULL"),
            sqlite_where=db.text("recompensa_aplicada_em IS NULL"),
        ),
    )


class Assinatura(db.Model):
    """Assinatura mensal de uma lanchonete (contrato anual de 12 parcelas).

    MVP: 1 assinatura ativa por lanchonete, ciclo anual fixo de 12 meses,
    sem upgrade/downgrade. Renovacao gera nova Assinatura com novo
    vigencia_inicio (process manual no admin no MVP).
    """
    __tablename__ = "assinaturas"

    STATUS_ATIVA      = "ativa"
    STATUS_SUSPENSA   = "suspensa"     # bloqueio temporario (inadimplencia em analise)
    STATUS_CANCELADA  = "cancelada"    # encerrada antes da vigencia (rescisao)
    STATUS_ENCERRADA  = "encerrada"    # ciclo de 12 meses concluido sem renovar

    STATUS_VALIDOS = (STATUS_ATIVA, STATUS_SUSPENSA, STATUS_CANCELADA, STATUS_ENCERRADA)

    id = db.Column(db.Integer, primary_key=True)
    lanchonete_id = db.Column(
        db.Integer, db.ForeignKey("lanchonetes.id"),
        nullable=False, index=True,
    )
    # Valor da mensalidade no momento do contrato. Snapshot — se preco
    # mudar no futuro, contratos antigos preservam o valor original.
    valor_mensal   = db.Column(Numeric(12, 2), nullable=False)
    parcelas_total = db.Column(db.Integer, nullable=False, default=12)
    vigencia_inicio = db.Column(db.Date, nullable=False)
    vigencia_fim    = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(20), nullable=False,
                       default=STATUS_ATIVA, index=True)
    criado_em = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    lanchonete = db.relationship("Lanchonete", backref="assinaturas")
    faturas = db.relationship(
        "Fatura", backref="assinatura",
        order_by="Fatura.parcela_numero",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('ativa','suspensa','cancelada','encerrada')",
            name="ck_assinatura_status_valido",
        ),
        CheckConstraint("valor_mensal > 0", name="ck_assinatura_valor_positivo"),
        CheckConstraint(
            "parcelas_total BETWEEN 1 AND 24",
            name="ck_assinatura_parcelas_range",
        ),
        CheckConstraint(
            "vigencia_fim >= vigencia_inicio",
            name="ck_assinatura_vigencia_ordem",
        ),
    )


class Fatura(db.Model):
    """Parcela mensal de uma Assinatura (12 por contrato no MVP).

    Admin marca como paga manualmente apos receber PIX/boleto fora do
    sistema. NF eh upload de PDF pelo admin (no MVP). Integracao com
    NFe.io / Notazz / Asaas fica pra v2.
    """
    __tablename__ = "faturas"

    STATUS_PENDENTE  = "pendente"
    STATUS_PAGA      = "paga"
    STATUS_ATRASADA  = "atrasada"      # vencido sem pagamento — script periodico marca
    STATUS_CANCELADA = "cancelada"     # parcela invalidada (rescisao, erro)

    STATUS_VALIDOS = (STATUS_PENDENTE, STATUS_PAGA, STATUS_ATRASADA, STATUS_CANCELADA)

    id = db.Column(db.Integer, primary_key=True)
    assinatura_id = db.Column(
        db.Integer, db.ForeignKey("assinaturas.id"),
        nullable=False, index=True,
    )
    parcela_numero = db.Column(db.Integer, nullable=False)  # 1..parcelas_total
    # Mes que a parcela cobre (ex: 2026-05-01 = "mai/2026"). Sempre
    # primeiro dia do mes pra simplificar agrupamento e evitar drift de TZ.
    mes_referencia = db.Column(db.Date, nullable=False, index=True)
    valor          = db.Column(Numeric(12, 2), nullable=False)
    vencimento     = db.Column(db.Date, nullable=False, index=True)
    status = db.Column(db.String(20), nullable=False,
                       default=STATUS_PENDENTE, index=True)

    pago_em      = db.Column(db.DateTime(timezone=True), nullable=True)
    pago_por_id  = db.Column(db.Integer, db.ForeignKey("usuarios.id"),
                             nullable=True, index=True)
    # Storage key do PDF da NF (mesmo padrao de comprovante_key em
    # ParticipacaoRodada). Admin sobe via /admin/financeiro/<fatura>/nf.
    nf_pdf_key      = db.Column(db.String(255), nullable=True)
    nf_emitida_em   = db.Column(db.DateTime(timezone=True), nullable=True)
    observacao      = db.Column(db.String(500), nullable=True)
    criado_em = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    pago_por = db.relationship("Usuario", foreign_keys=[pago_por_id])

    __table_args__ = (
        # Unica parcela N por assinatura (idempotencia da geracao em massa).
        UniqueConstraint("assinatura_id", "parcela_numero",
                         name="uq_fatura_assinatura_parcela"),
        CheckConstraint(
            "status IN ('pendente','paga','atrasada','cancelada')",
            name="ck_fatura_status_valido",
        ),
        CheckConstraint("valor > 0", name="ck_fatura_valor_positivo"),
        CheckConstraint(
            "parcela_numero BETWEEN 1 AND 24",
            name="ck_fatura_parcela_range",
        ),
        # Lista de inadimplentes do dashboard admin: hot path
        # (status='pendente' OR 'atrasada') AND vencimento <= hoje.
        db.Index("ix_fatura_status_vencimento", "status", "vencimento"),
    )


class Vendedor(db.Model):
    """SDR / vendedor da Aggron. 1-1 com Usuario tipo='vendedor'.

    Mesmo padrao de Lanchonete e Fornecedor (Usuario detem auth, modelo
    detem dados de negocio). Vendedor loga e ve apenas leads/clientes
    sob sua responsabilidade. Admin vê todos.
    """
    __tablename__ = "vendedores"

    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"),
                           nullable=False, unique=True)
    nome = db.Column(db.String(100), nullable=False)
    # Meta mensal de clientes fechados — referencia pro KPI no Kanban.
    meta_mensal_clientes = db.Column(db.Integer, nullable=False, default=10)
    ativo = db.Column(db.Boolean, default=True, nullable=False, index=True)
    criado_em = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    leads = db.relationship("Lead", backref="vendedor",
                            order_by="Lead.atualizado_em.desc()")

    __table_args__ = (
        CheckConstraint("meta_mensal_clientes > 0",
                        name="ck_vendedor_meta_positiva"),
    )


class Lead(db.Model):
    """Lead / prospect no pipeline comercial.

    Avanca pelas colunas do Kanban: frio (primeiro contato) -> morno
    (em conversa) -> quente (minuta enviada) -> fechado (assinou) ou
    cancelado (nao vai fechar, com motivo no log).
    """
    __tablename__ = "leads"

    STATUS_FRIO       = "frio"
    STATUS_MORNO      = "morno"
    STATUS_QUENTE     = "quente"
    STATUS_FECHADO    = "fechado"
    STATUS_CANCELADO  = "cancelado"

    STATUS_VALIDOS = (STATUS_FRIO, STATUS_MORNO, STATUS_QUENTE,
                      STATUS_FECHADO, STATUS_CANCELADO)
    STATUS_KANBAN_ORDEM = (STATUS_FRIO, STATUS_MORNO, STATUS_QUENTE,
                           STATUS_FECHADO, STATUS_CANCELADO)

    id = db.Column(db.Integer, primary_key=True)
    nome_estabelecimento = db.Column(db.String(150), nullable=False)
    nome_contato = db.Column(db.String(100))
    telefone = db.Column(db.String(20))
    email = db.Column(db.String(120))
    cidade = db.Column(db.String(80))
    cnpj = db.Column(db.String(18))  # opcional, ajuda na minuta
    observacoes = db.Column(db.String(500))

    vendedor_id = db.Column(db.Integer, db.ForeignKey("vendedores.id"),
                            nullable=False, index=True)
    status = db.Column(db.String(20), nullable=False,
                       default=STATUS_FRIO, index=True)

    # Quando lead vira "fechado" e SDR aciona "Converter em cliente",
    # populamos lanchonete_id pra rastrear conversao.
    lanchonete_id = db.Column(db.Integer, db.ForeignKey("lanchonetes.id"),
                              nullable=True, unique=True, index=True)

    criado_em = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False, index=True,
    )
    # atualizado_em muda em cada mudanca de status — usado pra calcular
    # "dias parado" no card do Kanban.
    atualizado_em = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    eventos = db.relationship("LeadEvento", backref="lead",
                              order_by="LeadEvento.criado_em.desc()",
                              cascade="all, delete-orphan")
    lanchonete = db.relationship("Lanchonete", foreign_keys=[lanchonete_id])

    __table_args__ = (
        CheckConstraint(
            "status IN ('frio','morno','quente','fechado','cancelado')",
            name="ck_lead_status_valido",
        ),
        # Hot path do Kanban: filtra (vendedor, status) ordenado por
        # atualizado_em pra mostrar coluna mais recente em cima.
        db.Index("ix_lead_vendedor_status_atualizado",
                 "vendedor_id", "status", "atualizado_em"),
    )


class LeadEvento(db.Model):
    """Log append-only de acoes comerciais sobre um lead.

    Cada visita, ligacao, reuniao, mudanca de status ou observacao
    gera 1 linha. Renderiza a timeline do detalhe do lead.
    """
    __tablename__ = "lead_eventos"

    TIPO_NOTA          = "nota"           # texto livre
    TIPO_MUDANCA_STATUS = "mudanca_status" # mudou coluna do Kanban
    TIPO_CONVERSAO     = "conversao"      # virou cliente

    id = db.Column(db.Integer, primary_key=True)
    lead_id = db.Column(db.Integer, db.ForeignKey("leads.id"),
                        nullable=False, index=True)
    autor_usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"),
                                 nullable=False, index=True)
    tipo = db.Column(db.String(30), nullable=False, default=TIPO_NOTA)
    descricao = db.Column(db.String(1000), nullable=False)
    criado_em = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False, index=True,
    )

    autor = db.relationship("Usuario", foreign_keys=[autor_usuario_id])


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
    TIPO_RODADA_EM_NEGOCIACAO    = "rodada_em_negociacao"
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
    criado_em = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)

    produto    = db.relationship("Produto")
    rodada     = db.relationship("Rodada", backref="catalogo")
    fornecedor_sugeriu = db.relationship("Fornecedor")

    __table_args__ = (
        db.Index("ix_rodada_produtos_rodada_aprovado",
                 "rodada_id", "aprovado"),
    )

    __table_args__ = (
        UniqueConstraint("rodada_id", "produto_id",
                         name="uq_rodada_produto"),
        # Fila admin "aprovar produtos sugeridos por fornecedores" — query
        # quente filtra aprovado IS NULL + adicionado_por_fornecedor_id IS NOT NULL.
        db.Index(
            "ix_rodada_produto_aprovacao_pendente",
            "rodada_id",
            postgresql_where=db.text(
                "aprovado IS NULL AND adicionado_por_fornecedor_id IS NOT NULL"
            ),
            sqlite_where=db.text(
                "aprovado IS NULL AND adicionado_por_fornecedor_id IS NOT NULL"
            ),
        ),
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


class AuditLog(db.Model):
    """Log estruturado de acoes do usuario pra rastreabilidade administrativa.

    Pega o que `EventoRodada` nao cobre: login/logout, CRUD de leads,
    produtos, lanchonetes, fornecedores, vendedores, mudancas de status
    fora do fluxo de rodada.

    Filosofia:
    - "acao" eh um codigo CURTO em snake_case (ex: 'login_ok', 'lead_criado',
      'lead_status_alterado'). Permite agregar/filtrar sem parsear texto livre.
    - "recurso_tipo" + "recurso_id" identificam o objeto afetado (opcional —
      acoes globais como 'login_ok' nao tem recurso).
    - "detalhes" guarda contexto adicional em texto curto (max 500 chars).
      Nunca salvar PII (senha, token, CPF) — usar mask_email/etc se preciso.
    - "ip" + "user_agent" pra forensics. Nullable (CLI/cron tem ambos null).

    Insert-only — auditoria nao se altera depois (idempotencia legal).
    """
    __tablename__ = "audit_log"

    # Acoes de auth
    ACAO_LOGIN_OK              = "login_ok"
    ACAO_LOGIN_FAIL            = "login_fail"
    ACAO_LOGOUT                = "logout"
    ACAO_SENHA_REDEFINIDA      = "senha_redefinida"
    # Acoes de CRM
    ACAO_LEAD_CRIADO           = "lead_criado"
    ACAO_LEAD_STATUS_ALTERADO  = "lead_status_alterado"
    ACAO_LEAD_CONVERTIDO       = "lead_convertido"
    ACAO_LEAD_EVENTO           = "lead_evento_adicionado"
    # Acoes admin de cadastro
    ACAO_PRODUTO_CRIADO        = "produto_criado"
    ACAO_PRODUTO_EDITADO       = "produto_editado"
    ACAO_LANCHONETE_CRIADA     = "lanchonete_criada"
    ACAO_FORNECEDOR_CRIADO     = "fornecedor_criado"
    ACAO_VENDEDOR_CRIADO       = "vendedor_criado"
    # Acoes admin de rodada (alem do EventoRodada)
    ACAO_RODADA_CRIADA         = "rodada_criada"
    ACAO_RODADA_CANCELADA      = "rodada_cancelada"
    ACAO_RODADA_FINALIZADA     = "rodada_finalizada"
    # Acoes admin de financeiro
    ACAO_FATURA_PAGA           = "fatura_paga"
    ACAO_FATURA_PENDENTE       = "fatura_pendente"

    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer,
        db.ForeignKey("usuarios.id", name="fk_audit_usuario"),
        nullable=True, index=True)  # null = anonimo (login_fail sem user)
    acao = db.Column(db.String(50), nullable=False, index=True)
    recurso_tipo = db.Column(db.String(40), index=True)  # ex: 'lead', 'produto'
    recurso_id   = db.Column(db.Integer)
    detalhes  = db.Column(db.String(500))
    ip        = db.Column(db.String(45))  # IPv6 max
    user_agent = db.Column(db.String(255))
    criado_em = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False, index=True,
    )

    usuario = db.relationship("Usuario")

    __table_args__ = (
        # Filtro mais comum: por usuario + ordem cronologica.
        db.Index("ix_audit_usuario_data", "usuario_id", "criado_em"),
    )