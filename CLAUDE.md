# PoolCompras — guia do Claude Code

## O que é o projeto
Central de compras cooperativa para hamburguerias de Londrina. Lanchonetes fazem pedidos, sistema agrega, socios (Mateus + Ademar) cotam com fornecedores. Volume agregado = preco menor.

**Repo:** https://github.com/mateusrfabro/poolcompras
**Pasta local:** `C:/Users/NITRO/Projects/poolcompras`
**Stack:** Flask + SQLAlchemy + Alembic + Jinja2 + CSS vanilla + JS vanilla CSP-safe

## Socios e papeis
- **Mateus** (voce esta interagindo com ele): tech lead, desenvolve as features
- **Ademar**: socio infra/negocios, faz o papel de PO — manda feedback via WhatsApp com prints e texto. Valoriza simplicidade, detalhista em fluxos, cobra qualidade ("tem que ficar redondo")

## 3 perfis do sistema
1. **Admin** (Mateus + Ademar futuramente): gerencia tudo — rodadas, produtos, fornecedores, lanchonetes, moderacao, aprovacoes
2. **Lanchonete**: faz pedidos, aceita/recusa propostas, paga, avalia
3. **Fornecedor**: cota precos (partida + final), negocia com admin, recebe pagamentos

## Ambiente de execucao
- **Python 3.12:** `C:/Users/NITRO/AppData/Local/Programs/Python/Python312/python.exe`
  - 314 existe no PATH mas falta pacotes — sempre 3.12
- **Rodar Flask:** `python run.py > /tmp/flask.log 2>&1 &`
- **Ngrok:** `ngrok http 5050 --log=stdout > /tmp/ngrok.log 2>&1 &`
- **DB dev:** SQLite em `instance/poolcompras.db`
- **Testes:** `python -m pytest tests/ -q`

## Logins de teste
| Perfil | Email | Senha |
|---|---|---|
| Admin | admin@poolcompras.com | admin123 |
| Lanchonete principal | smash@demo.com | demo123 |
| Fornecedor principal | vendas@dsulcarnes.demo | demo123 |

9 lanchonetes + 4 fornecedores adicionais com `@demo.com` / `demo123`.

## Fluxo completo da rodada
```
1. Admin cria rodada                               status=preparando
2. Admin monta catalogo (seleciona produtos)       preparando
3. Admin envia aos fornecedores                    aguardando_cotacao
4. Fornecedor coloca PRECO DE PARTIDA              aguardando_cotacao
5. Admin aprova sugestoes de produto novo (se houver)  aberta
6. Lanchonete escolhe itens + qtds (Salvar rascunho)   aberta
7. Lanchonete ENVIA pedido pra moderacao           aberta + pedido_enviado_em
8. Admin MODERA pedido: Aprovar/Devolver/Reprovar/Reverter  aberta + pedido_aprovado_em
9. Admin encerra coleta                            em_negociacao
10. Fornecedor cota PRECO FINAL (com volumes reais)    em_negociacao
11. Fornecedor ENVIA cotacao pra aprovacao         em_negociacao + submissao.enviada_em
12. Admin APROVA cotacao (ou Devolve com nota de negociacao)  submissao.aprovada_em
13. Lanchonete ACEITA proposta (parcial ou total, assim que submissao aprovada)
14. Admin finaliza rodada                          finalizada
15. Lanchonete paga, recebe, avalia                finalizada
```

## Squad de agentes (.claude/agents/squad-pool-compras/)
- **backend-dev** — desenvolve features Flask respeitando arquitetura
- **product-manager** — destila feedback do Ademar em specs acionaveis
- **tester** — escreve e mantem testes pytest
- **database** — modelagem SQLAlchemy + Alembic + performance
- **code-quality** — auditoria de qualidade Python/Flask
- **ux-review** — revisao frontend SEM alterar identidade visual
- **security** — OWASP Top 10 adaptado Flask
- **devops** — deploy, Docker, Nginx, CI/CD (ativa no Bloco D)

Use via `Task` tool com `subagent_type`.

## Como Claude deve operar aqui

### Antes de qualquer task
1. Ler este arquivo (CLAUDE.md)
2. Ler `MEMORY.md` do projeto (aprendizados consolidados)
3. Checar estado git: `git status` + `git log --oneline -5`
4. Se o usuario mandou feedback do Ademar (print WhatsApp): usar agente `product-manager` pra destilar spec primeiro

### Durante implementacao
1. Tipo de mudanca? feature/fix/refactor/docs/test/chore
2. Afeta modelo? Precisa migration Alembic
3. Afeta rotas? Pensar IDOR + CSRF + decorators de papel
4. Afeta template? Respeitar identidade visual (paleta laranja, cards claros)
5. Escrever/atualizar teste correspondente
6. Rodar `pytest tests/ -q` — deve passar 100%
7. Smoke HTTP com requests contra localhost:5050
8. Commit granular: `feat:`, `fix:`, `refactor:`, `test:`, `docs:`, `chore:`

### Padroes inviolaveis
- **NUNCA** `Model.query.get(id)` — usar `db.session.get(Model, id)` (SQLAlchemy 2.0)
- **NUNCA** import `from app.models import X` dentro de funcao — UnboundLocalError
- **NUNCA** Float pra dinheiro — sempre `Numeric(12, 2)`
- **NUNCA** commitar `.env` ou credenciais
- **NUNCA** alterar identidade visual sem autorizacao (paleta laranja do PoolCompras)
- **NUNCA** usar `onclick=` inline (CSP bloqueia) — JS externo em `app/static/js/`
- **NUNCA** deploy/push force sem autorizacao explicita

### Regras de comunicacao
- Respostas curtas e diretas (Mateus valoriza concisao)
- Listar o que fez em bullets quando entregar
- Apontar riscos antes de implementar quando houver ambiguidade
- Ofercer **default** concreto em vez de pergunta aberta

## Arquitetura
```
app/
  __init__.py      # create_app(), filtros Jinja, config por env
  models.py        # 12 modelos (1 arquivo ate crescer)
  routes/          # controllers por dominio
    admin.py       # ~900 linhas (dividir em submodulos e divida tecnica)
    fornecedor.py  # cotacao + negociacao
    pedidos.py     # catalogo lanchonete + Salvar/Enviar
    historico.py   # Minhas rodadas + detalhe + analytics
    rodadas.py     # Detalhe publico da rodada
    fluxo.py       # Aceitar/recusar/pagar/entregar
    main.py        # Dashboard + health
    auth.py        # Login/logout/signup
    uploads.py     # Download autenticado
  services/        # Logica de negocio extraida
    pendencias.py
    dashboard_lanchonete.py
    csv_export.py
    storage.py
  templates/       # Jinja2 por dominio
  static/
    css/style.css  # Variaveis e classes reutilizaveis
    js/            # Externos, CSP-safe
migrations/versions/  # 8 migrations aplicadas
tests/             # ~43 testes (auth/fluxo/security/moderacao/filters)
```

## Features-chave implementadas
- Fluxo de moderacao de pedidos (admin aprova/devolve/reprova/reverte)
- Cotacao em 2 etapas (preco de partida + preco final com volumes reais)
- Aprovacao de cotacao final + chat de negociacao admin<->fornecedor (append-only)
- Economia calculada automaticamente (por produto e total da rodada)
- Quick wins: repetir ultimo pedido, historico precos SKU, funil conversao
- Filtros de invisibilidade: nao-aprovados ficam ocultos pro fornecedor
- Sub-nav padronizada nos 3 perfis
- Countdown humanizado + urgencia visual (< 24h)
- Mascara R$ em todos campos de preco

## Backlog aberto
### Tecnico
- Dividir `admin.py` em submodulos (900+ linhas)
- Flask-Caching nos KPIs (quando tiver producao)
- Cobertura de testes para fluxo novo de aprovacao de cotacao
- Mais testes de IDOR nos endpoints novos

### Produto
- Alertas WhatsApp via Z-API
- "Meu P&L" pro fornecedor + "Meu CMV" pra lanchonete
- Marketplace publico com rating

### Deploy (Bloco D — aguardando VM do Ademar)
- nginx + Let's Encrypt
- Gunicorn multi-worker
- Redis pra Flask-Limiter
- Postgres em prod
- GitHub Actions CI/CD

## Gotchas conhecidos
1. **Import dentro de funcao** — UnboundLocalError. Sempre topo do arquivo.
2. **Session resume mata Flask** — subir de novo manualmente.
3. **Python 314 falta pacotes** — sempre usar 3.12.
4. **SQLite batch mode exige FK name** — nao deixar `None` em migrations.
5. **Admin.py grande** — cuidado ao editar, usar Grep antes de Edit.

## Decisoes arquiteturais importantes
1. **Fluxo novo substituiu o antigo** (nao ha fallback). Rodadas antigas rodam com dados legados.
2. **2 niveis de categoria** (categoria + subcategoria obrigatorias no produto).
3. **Admin pode selecionar do catalogo existente.** Fornecedor sugere novo; admin aprova.
4. **Somente admin cancela rodada.**
5. **Fornecedor ve rodada COMO UM TODO, nao por lanchonete individual.** Pendencias agrupadas por rodada.
6. **Pagamento e FORA do sistema.** PoolCompras so guarda o comprovante.
7. **Dados bancarios do fornecedor** sao exibidos pra lanchonete na hora de pagar.
8. **Aprovacao de cotacao individual** — cada fornecedor aprovado ja libera aceite parcial pra lanchonete.
9. **Notas de negociacao append-only** — nao eh chat, eh campo de texto + historico com timestamp+autor.