# Memoria do projeto PoolCompras

Sistema de memoria persistente pra aprendizados consolidados do projeto.
Claude Code deve ler este arquivo no inicio de cada sessao.

## Feedback acumulado do usuario (Mateus)

### Estilo de comunicacao
- Respostas **curtas e diretas**, nada de enrolar
- Bullets quando entregar resumo
- Nao explicar o que ja foi pedido — ir direto ao ponto
- Quando tiver ambiguidade, **propor default concreto** em vez de pergunta aberta
- Gosta de ver o **git log** atualizado e o **teste rodando** depois de cada feature

### Preferencias tecnicas
- Flask + Jinja + CSS vanilla — **nao introduzir framework** JS (React, Vue, etc)
- Manter paleta laranja do PoolCompras — **NAO alterar identidade visual** sem autorizacao
- Prefere **commits granulares** com mensagem descritiva
- Pytest sempre que possivel — NAO aceita merge sem teste novo pra feature nova

### Padroes de deploy
- **git commit + push** apos cada feature valida
- **Nunca** force push
- **Nunca** skip hooks
- **Nunca** commitar `.env` ou credenciais

## Aprendizados tecnicos (bugs encontrados + licoes)

### 1. Import dentro de funcao causa UnboundLocalError
`from app.models import X` dentro de def marca X como local em TODA a funcao.
Se usado antes em ramo condicional -> UnboundLocalError.

**Regra:** Imports SEMPRE no topo do arquivo.

Incidente: rota `/rodadas/<id>` dava erro 500 pra nao-admin (18/04/2026).

### 2. SQLite batch mode exige FK nomeada
`batch_op.create_foreign_key(None, ...)` em migration quebra no SQLite:
`ValueError: Constraint must have a name`.

**Regra:** sempre nomear: `batch_op.create_foreign_key('fk_tabela_col', ...)`.

### 3. Query.get() legacy em SQLAlchemy 2.0
`Model.query.get(id)` gera `LegacyAPIWarning`. Preferir:
`db.session.get(Model, id)`.

### 4. datetime.utcnow() deprecated
Gera `DeprecationWarning`. Preferir:
`datetime.now(timezone.utc)` — mas ao salvar em DB sem timezone, usar:
`datetime.now(timezone.utc).replace(tzinfo=None)`.

### 5. Decimal * float = TypeError
`Numeric(12,2)` SQLAlchemy retorna Decimal. Operar com float da erro.

**Regra:** converter antes: `float(decimal_val) * x`.

### 6. Cotacao.preco_unitario eh preco FINAL, nao partida
- `Cotacao.preco_unitario` = preco final do fornecedor
- `RodadaProduto.preco_partida` = preco de referencia da fase 1

Bug detectado 18/04: historico.py usava `max/min` de Cotacao achando que era partida/final.

### 7. Variaveis nao definidas em ramos condicionais
Inicializar vars ANTES do `if` quando sao passadas pro template depois.

Bug: `cotacoes_pendentes_aprovacao` so definida dentro de `if current_user.is_admin:` quebra render pra nao-admin.

## Patterns arquiteturais consolidados

### Services para logica de negocio
Controllers ficam finos. Logica reutilizavel vai pra `app/services/`.
Exemplos: `dashboard_lanchonete.py`, `pendencias.py`.

### Filtros Jinja customizados
Formatacao centralizada em `app/__init__.py`:
- `|brl` — R$ 1.234,56
- `|qtd` — remove .0 de inteiros
- `|fmt_un` — 5 kg / 1 fardo (pluraliza)
- `|status_label` — traduz status PT-BR
- `|countdown` — "Fecha em 3h45min" / "Encerrada"
- `|datetime_br` — "18/04/2026 as 23:59"
- `|urgente` — boolean se deadline <= 24h

### Moderacao em 2 lados
- Pedidos de lanchonete: admin aprova/devolve/reprova/reverte
- Cotacoes de fornecedor: admin aprova/devolve com notas de negociacao
- Em ambos: **filtros de invisibilidade** — nao-aprovados somem pro outro lado

### Sub-nav padronizada
Admin (Painel | Analytics), Lanchonete (Painel | Meu Resumo), Fornecedor (Painel | Meu Desempenho).

## Fluxos criticos documentados

### Fluxo de pedido (lanchonete)
```
Salvar rascunho -> Enviar pra moderacao -> Admin Aprova/Devolve/Reprova
                                           |
                                           Devolvido: ajusta + reenvia
                                           Reprovado: bloqueado
                                           Aprovado: entra no pool
```

### Fluxo de cotacao (fornecedor)
```
Fase 1: preco de partida (sem volumes) -> rodada abre pra lanchonetes
Fase 2 (em_negociacao): preco final (com volumes reais)
  -> Enviar pra aprovacao
  -> Admin Aprova ou Devolve (com chat append-only)
  -> Aprovado: disponivel pra lanchonetes aceitarem
```

### Visibilidade de status
Status das submissoes de cotacao aparece em **todos os perfis** na tela de detalhe da rodada (tabela "Status das cotacoes finais").

## Rotas mapeadas

### Admin
- `/admin/produtos` CRUD + `/admin/produtos/<id>/historico-precos`
- `/admin/fornecedores` CRUD
- `/admin/lanchonetes` CRUD
- `/admin/rodadas/<id>/catalogo` montar
- `/admin/rodadas/<id>/moderar-pedidos` aprovar/devolver/reprovar/reverter
- `/admin/rodadas/<id>/aprovar-cotacoes` aprovar/devolver + notas
- `/admin/rodadas/<id>/aprovar-produtos` sugestoes de fornecedor
- `/admin/rodadas/<id>/funil` analise de conversao
- `/admin/analytics` KPIs gerais
- `/admin/relatorio` consolidado por periodo + CSV
- `/admin/historico-aprovacoes` produtos sugeridos (historico)
- `/admin/submissoes/<id>/nota` adicionar nota

### Lanchonete
- `/pedidos/catalogo` Salvar/Enviar
- `/pedidos/repetir-ultimo-pedido` 1-clique
- `/minhas-rodadas/` + `/minhas-rodadas/<id>` + `/minhas-rodadas/analytics`
- `/rodadas/<id>/aceitar` + `/rodadas/<id>/recusar`

### Fornecedor
- `/fornecedor/dashboard` painel
- `/fornecedor/analytics` meu desempenho
- `/fornecedor/rodada/<id>` ver demanda agregada (so aprovados)
- `/fornecedor/rodada/<id>/cotar-catalogo` preco partida
- `/fornecedor/rodada/<id>/cotacao-final` preco final + enviar
- `/fornecedor/rodada/<id>/cotacao-final/nota` nota negociacao

## Checklist padrao antes de entregar feature
1. [ ] Teste novo pra caminho feliz
2. [ ] Teste pra edge case (vazio, invalido)
3. [ ] Teste de IDOR se aplicavel
4. [ ] `pytest tests/ -q` 100% passando
5. [ ] Smoke HTTP com requests contra localhost:5050
6. [ ] Logs sem erro (`grep -c traceback /tmp/flask.log` = 0)
7. [ ] Commit granular com mensagem descritiva
8. [ ] Push origin main

## Contatos e infra
- **Repo:** https://github.com/mateusrfabro/poolcompras
- **Socio infra:** Ademar (Yggdrasil — Windows 11 + Docker + WSL2 + Tailscale)
- **Deploy previsto:** VM Ubuntu na rede do Ademar (Bloco D, em espera)
- **Ngrok atual:** https://reckless-swinger-scanning.ngrok-free.dev (dev)