# Carga (Locust)

Suite de teste de carga rodando o caminho critico do Aggron.

## Quando rodar

- **Antes** de abrir cadastros pra novas lanchonetes/fornecedores
- **Antes** de mudar config do gunicorn (workers, threads)
- **Antes** de subir Postgres em prod
- **Apos** mudancas estruturais em rotas hot (dashboard, catalogo, P&L)

## Quando NAO rodar

- **Nunca em producao** — vai abrir pedidos e cotacoes reais no banco
- **Nunca contra Yggdrasil sem aviso** — Ademar precisa saber que vai sofrer carga

## Pre-requisitos

```bash
pip install -r requirements-dev.txt   # instala locust 2.32.4
```

App alvo precisa ter os seeds de dev:
- `admin@aggron.com.br` / `admin123`
- `smash@demo.com` / `demo123`
- `vendas@dsulcarnes.demo` / `demo123`

Se o banco esta vazio, roda primeiro:
```bash
flask seed dev    # ou seu script equivalente
```

## Como rodar

### UI interativa (browser em localhost:8089)

```bash
# Inicia Flask em outro terminal
python run.py

# Roda Locust
locust -f tests/load/locustfile.py --host=http://localhost:5050
```

Abre `http://localhost:8089` e configura:
- Number of users: 50
- Spawn rate: 5 (5 users novos por segundo)
- Run time: deixa rodar 2-5 minutos

### Headless (CI / shell)

```bash
locust -f tests/load/locustfile.py \
       --host=http://localhost:5050 \
       --users=50 \
       --spawn-rate=5 \
       --run-time=2m \
       --headless
```

## Cenarios

| Classe | Peso | Caminho |
|---|---|---|
| `LanchoneteUser` | 50% | dashboard + catalogo + listar pedidos + historico |
| `FornecedorUser` | 30% | dashboard + analytics + P&L |
| `AdminUser` | 20% | rodadas + fornecedores + lanchonetes + analytics + relatorio |

Todos os cenarios sao **read-only** (so GETs). Nao criamos pedidos nem
cotacoes na carga — isso poluiria o banco e mudaria o estado entre runs.

Escrita real exige cenario com setup/teardown dedicado.

## Metricas alvo

Em hardware de dev (Ryzen 5 / 16GB):

| Metrica | Alvo | Critico |
|---|---|---|
| p50 (mediana) | < 200ms | < 500ms |
| p95 | < 800ms | < 2000ms |
| Falhas | 0 | < 1% |
| Pool DB esgota | nunca | nunca (config `db_pool` precisa segurar) |

Se p95 > 2s ou houver 500s, parar e investigar antes de subir features novas.

## Como interpretar

- **/dashboard** sendo o mais lento eh esperado (KPIs + agregacao). Se p95
  passar de 1s, candidato a Flask-Caching com TTL curto.
- **/pedidos/catalogo** pode estourar com muitos produtos. Indice em
  `produto.categoria` ja existe; se ainda for lento, paginar.
- **/fornecedor/pnl** agrega vendas. Se for o gargalo com muitas rodadas
  finalizadas, considera materializar o resumo.

## Troubleshooting

- **Tudo retornando 302**: login falhou. Verifica se os seeds existem.
- **CSRF token errors**: a regex `CSRF_RE` no locustfile pode ter desatualizado;
  confere se ainda bate com `name="csrf_token" value="...">` no HTML.
- **Connection refused**: Flask nao esta rodando ou esta em outra porta.
