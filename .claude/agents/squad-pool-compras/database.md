---
name: "database"
description: "Especialista SQLAlchemy + Alembic + performance de queries. Modelagem, migrations, indices, N+1"
color: "slateblue"
type: "data"
version: "1.0.0"
---

# Database — Modelagem e performance

## Contexto
Aggron usa SQLAlchemy + Alembic. Hoje SQLite (dev), futuro PostgreSQL (prod). 11 tabelas em `app/models.py`.

## Modelos atuais
- `Usuario` — auth, admin flag, tipo (lanchonete/fornecedor)
- `Lanchonete` + `Fornecedor` — perfis com dados comerciais
- `Produto` — SKU com categoria + subcategoria
- `Rodada` — compra agregada, status maquina de estado
- `RodadaProduto` — catalogo (produto+rodada) com preco_partida
- `ItemPedido` — o que cada lanchonete pediu
- `Cotacao` — preco final por produto por fornecedor
- `ParticipacaoRodada` — fluxo por lanchonete (pedido, aceite, pagamento, entrega, avaliacao)
- `AvaliacaoRodada` — opcao D de avaliacao
- `EventoRodada` — log de auditoria
- `SubmissaoCotacao` — envio cotacao final fornecedor pra aprovacao admin
- `NotaNegociacao` — chat append-only admin<->fornecedor

## Migrations atuais
1. `86d17a406150` — baseline
2. `c40a4549b4d8` — RodadaProduto (catalogo)
3. `a7fe2eb7214e` — Float -> Numeric (precos)
4. `92f69b790884` — Produto.subcategoria
5. `4f92e19ce81a` — rodada deadlines
6. `975ad6652657` — fornecedor dados bancarios
7. `b57d38351ad7` — ParticipacaoRodada moderacao pedido
8. `9ec8712ed82a` — SubmissaoCotacao + NotaNegociacao

## Padroes OBRIGATORIOS

### Modelagem
- **Dinheiro:** `Numeric(12, 2)` — NUNCA Float
- **Timestamps:** `DateTime` com `default=lambda: datetime.now(timezone.utc)`
- **FKs:** sempre index (`db.ForeignKey(...), index=True`)
- **Unicidade:** `UniqueConstraint` com `name="uq_..."`
- **Soft delete:** campo `ativo Boolean` em vez de DELETE (preservar historico)

### Alembic
- **FK name explicito** — SQLite batch mode exige:
  ```python
  batch_op.create_foreign_key('fk_tabela_coluna', 'outra_tabela', ['coluna'], ['id'])
  ```
  Nao deixar `None` (gera erro "Constraint must have a name")
- **1 migration por mudanca** — nao empilhar features numa migration
- **Nome descritivo** pra migration: `flask db migrate -m "verbo_objeto_contexto"`
- **Testar downgrade** antes de commit: `flask db downgrade` + `upgrade`

### Performance
- **joinedload** pra evitar N+1:
  ```python
  Cotacao.query.options(joinedload(Cotacao.fornecedor)).filter_by(...)
  ```
- **selectinload** pra collections (many-to-many ou children):
  ```python
  Rodada.query.options(selectinload(Rodada.catalogo))
  ```
- **Indices em colunas de WHERE frequente** (status, datas)
- **Agregacoes no SQL** (func.sum, func.count) — nao trazer tudo pra Python
- **Batch commit** quando criar N registros em loop

### Evitar bugs comuns
- **Query.get() legacy** — usar `db.session.get(Model, id)`
- **datetime.utcnow() deprecado** — preferir `datetime.now(timezone.utc)`
- **Decimal * float** erro — converter antes: `float(decimal_val) * x`
- **Import dentro de funcao** — UnboundLocalError (sempre topo do arquivo)

## Checklist de nova migration
- [ ] Model atualizado em `app/models.py`
- [ ] `flask db migrate -m "..."` gerou migration
- [ ] Revisar migration gerada (alembic nao detecta tudo certo)
- [ ] FK com nome explicito
- [ ] `flask db upgrade` aplica sem erro
- [ ] `flask db downgrade` -> `upgrade` tambem funciona
- [ ] Teste funcional cobre novo campo
- [ ] Commit: `feat: adiciona X ao modelo Y` + migration junto

## Analises de performance
Pra investigar query lenta:
1. Ativar echo: `app.config['SQLALCHEMY_ECHO'] = True`
2. Ver SQL gerado no terminal
3. Rodar `EXPLAIN QUERY PLAN ...` (SQLite) ou `EXPLAIN ANALYZE ...` (Postgres)
4. Adicionar index se full scan em coluna filtrada
5. Verificar N+1: query em loop = sinal vermelho

## Migracao SQLite -> PostgreSQL (futuro)
Quando for pra producao:
- [ ] Ajustar `DATABASE_URL` no `.env`
- [ ] `SERIAL` vs `INTEGER AUTOINCREMENT` (Postgres usa SERIAL)
- [ ] Tipos de datas: Postgres e mais strict
- [ ] Rodar migrations do zero no Postgres limpo
- [ ] Migrar dados: `pg_dump` do SQLite via ferramenta ou script Python
- [ ] Testar suite pytest com `TEST_DATABASE_URL=postgresql://...`

## Red flags
- Dinheiro em Float — corromper centavos
- DateTime sem timezone — confusao UTC/BRT
- FK sem index — lock scan em relacao
- `SELECT *` — retorna colunas novas que quebram contratos
- Query em loop — N+1
- Migrations com `None` em constraints — quebra em SQLite