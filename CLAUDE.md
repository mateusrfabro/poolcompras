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
4. Afeta template? Respeitar identidade visual (paleta azul corporativa #1D3557, verde alimento #2A9D8F como acento, cards claros — rebrand abr/2026)
5. Escrever/atualizar teste correspondente
6. Rodar `pytest tests/ -q` — deve passar 100%
7. Smoke HTTP com requests contra localhost:5050
8. Commit granular: `feat:`, `fix:`, `refactor:`, `test:`, `docs:`, `chore:`

### Padroes inviolaveis
- **NUNCA** `Model.query.get(id)` — usar `db.session.get(Model, id)` (SQLAlchemy 2.0)
- **NUNCA** import `from app.models import X` dentro de funcao — UnboundLocalError
- **NUNCA** Float pra dinheiro — sempre `Numeric(12, 2)`
- **NUNCA** commitar `.env` ou credenciais
- **NUNCA** alterar identidade visual sem autorizacao (paleta azul corporativa do PoolCompras pos-rebrand B2B)
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
    admin/         # pacote (rodadas, moderacao, fornecedores, lanchonetes, produtos, analytics, ...)
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
    notificacoes.py     # Telegram bot + helpers em massa por transicao de status
    pnl_fornecedor.py
    rodada_corrente.py
  templates/       # Jinja2 por dominio
  static/
    css/style.css  # Variaveis (--space-*, --font-*, paleta) e classes
    js/            # Externos, CSP-safe
migrations/versions/  # 18 migrations aplicadas
tests/             # ~280 testes (auth/fluxo/security/moderacao/filters/notif/auto-save)
tests/load/        # Suite Locust (carga simulada — nao roda em CI)
```

## Features-chave implementadas
- Fluxo de moderacao de pedidos (admin aprova/devolve/reprova/reverte) com guards de idempotencia
- Cotacao em 2 etapas (preco de partida + preco final com volumes reais)
- Aprovacao de cotacao final + chat de negociacao admin<->fornecedor (append-only)
- Economia calculada automaticamente (por produto e total da rodada)
- Quick wins: repetir ultimo pedido, historico precos SKU, funil conversao
- Filtros de invisibilidade: nao-aprovados ficam ocultos pro fornecedor
- Sub-nav padronizada nos 3 perfis
- Countdown humanizado + urgencia visual (< 24h)
- Mascara R$ em todos campos de preco
- Meu P&L (fornecedor) + Meu CMV (lanchonete)
- Notificacoes Telegram em todas transicoes-chave de rodada (catalogo enviado, aberta, em_negociacao, cotacao aprovada, cancelada) + moderacao individual
- Rebrand corporativo B2B (azul + Inter/Montserrat + container 1200px + sistema 8px)
- Suite de carga Locust (3 cenarios em tests/load/)

## Backlog aberto
### Tecnico
- Locust contra Yggdrasil (revalidar perf real apos Argon2 + cache + Redis)
- Field-errors em mais forms admin (produto, fornecedor, lanchonete) — padrao ja criado, aplicado em login + 3 fluxos auth
- Cache nos KPIs do dashboard fornecedor/lanchonete (hoje so admin)

### Produto
- Aguardar feedback Ademar pos-deploy
- Templates/visual logado pode receber mesmo polishment SVG da home publica

### Deploy
- Postgres em prod: ✅ Yggdrasil (Ademar)
- Cloudflare Tunnel: ✅ (substituiu nginx + Let's Encrypt)
- Gunicorn multi-worker: ✅ (2*CPU+1, max-requests 1000+jitter)
- Redis pra Flask-Limiter: ✅ (compose com servico redis, RATELIMIT_STORAGE_URI no env)
- GitHub Actions CI/CD: ✅ (pytest a cada push/PR)

## Gotchas conhecidos
1. **Import dentro de funcao** — UnboundLocalError. Sempre topo do arquivo.
2. **Session resume mata Flask** — subir de novo manualmente.
3. **Python 314 falta pacotes** — sempre usar 3.12.
4. **SQLite batch mode exige FK name** — nao deixar `None` em migrations.
5. **SQLite vs Postgres em migrations**: usar `TRUE`/`FALSE` em UPDATE de coluna boolean; SQLite aceita `1`/`0` mas Postgres eh tipo-estrito (incidente real R5).
6. **Notif Telegram eh best-effort**: helper retorna False se canal nao configurado e nao bloqueia o fluxo. Sempre commitar DB antes de chamar `notificar_*`.

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
10. **Notificacoes em transicoes de status sao em massa**: `notificar_fornecedores_nova_rodada` e similares iteram `Fornecedor.ativo=True` / `Lanchonete.ativa=True`. Sao sincronas hoje (best-effort). Em alta carga (50+ users), considerar fila/queue.
11. **Guards de idempotencia em moderacao**: aprovar/devolver/reprovar/reverter (tanto pedido quanto cotacao) tem guard explicito que retorna sem mutar nem disparar notif quando ja esta no estado terminal — protege contra 2 cliques rapidos / 2 admins simultaneos.