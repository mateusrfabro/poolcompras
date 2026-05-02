# Como conectar o Telegram ao Aggron

Bot gratuito — sem custo mensal, sem templates aprovados, sem Z-API.

## Parte 1 — Criar o bot (Mateus, 1x)

1. Abra o Telegram e procure por **@BotFather**.
2. Envie `/newbot`.
3. Responda com **nome de exibição** (ex: `Aggron`).
4. Responda com **username** terminando em `bot` (ex: `AggronBot`).
5. BotFather vai mandar o **token** — guarde.

## Parte 2 — Configurar o token no servidor

Em dev local (arquivo `.env` do projeto, que está no `.gitignore`):
```
TELEGRAM_BOT_TOKEN=123456789:ABC-DEF...
```

Em prod (systemd, variável de ambiente da VM):
```bash
export TELEGRAM_BOT_TOKEN="123456789:ABC-DEF..."
```

Sem a variável setada, o Aggron cai em fallback (loga no servidor).

## Parte 3 — Usuário vincula (UX automática — 3 cliques)

1. Logar no Aggron → **Meu perfil**.
2. Clicar **Conectar Telegram** → sistema abre o bot `@poolcomprasbot`
   no Telegram com um token de vinculação embutido.
3. No Telegram, apertar **Iniciar** (ou enviar `/start`).
4. Voltar no Aggron → clicar **Já dei /start, concluir** → sistema
   descobre o chat_id automaticamente e envia uma mensagem de confirmação.

Pronto. A vinculação é 1-via-1 (o token só serve pro usuário que pediu).
TTL de 10 min — se passar disso, basta clicar "Conectar Telegram" de novo.

### Fallback manual

Se por algum motivo o fluxo automático não funcionar (proxy bloqueando,
múltiplos usuários clicando ao mesmo tempo esgotando `getUpdates`, etc),
há um toggle **"Prefere colar o chat_id manualmente?"** dentro de
Meu Perfil. Nele o usuário pode:

1. No Telegram, abrir `@userinfobot` e mandar `/start` → recebe o Id.
2. Colar o Id no campo e salvar.
3. Falar `oi` pro `@poolcomprasbot` (abre conversa).

## Parte 4 — Validar

Ao conectar, o sistema envia uma mensagem "<b>Telegram conectado!</b>".
Se não chegou, o log do servidor diz o motivo:

| Log | Significa |
|---|---|
| `TELEGRAM_OK usuario=X` | Chegou. |
| `TELEGRAM_FAIL ... 403` | Usuário bloqueou o bot. |
| `NOTIF_FALLBACK` | Token não setado ou chat_id vazio. |
| `TELEGRAM_GET_UPDATES_FAIL` | Token errado ou API fora. |

## Eventos que notificam

| Evento | Quem recebe |
|---|---|
| Reset de senha | Dono do e-mail |
| Pedido aprovado/devolvido/reprovado | Lanchonete |
| Cotação final aprovada/devolvida | Fornecedor |
| Comprovante de pagamento enviado | Fornecedor(es) vencedor(es) |
| Pagamento confirmado | Lanchonete |
| Entrega informada | Lanchonete |

## Webhook (produção com URL HTTPS pública)

Código do webhook já está em `app/routes/telegram_webhook.py`. Quando a VM
Ademar estiver no ar:

### 1. Env vars

```
TELEGRAM_BOT_TOKEN=123456:ABC...
TELEGRAM_WEBHOOK_URL=https://poolcompras.xyz          # base HTTPS publica
TELEGRAM_WEBHOOK_SECRET=<32+ chars aleatorios>        # gere com openssl rand -hex 32
```

### 2. Registrar webhook no Telegram

```bash
flask telegram set-webhook       # registra https://<URL>/webhook/telegram/<secret>
flask telegram info              # mostra url atual + pendencias + ultimo erro
flask telegram remove-webhook    # volta pro modo getUpdates (dev)
```

### 3. Efeitos na UX

Com webhook ativo, a vinculação fica **100% automática**:

1. User clica "Conectar Telegram" → abre `t.me/poolcomprasbot?start=<token>`
2. No Telegram, aperta "Iniciar"
3. Webhook recebe, valida token, salva `chat_id`, bot responde "Conectado!"
4. User volta no site, clica "Já dei /start, concluir" → sistema detecta
   que o `chat_id` já foi salvo e confirma sem precisar de OTP

Sem webhook, o fluxo cai em `getUpdates` on-demand + OTP — continua
funcionando, mas exige 1 clique a mais e tem race condition multi-user.

### 4. Segurança

- URL tem secret path (`/webhook/telegram/<secret>`) — sem secret correto
  retorna 404 (não revela existência).
- Rota isenta de CSRF (Telegram não manda token).
- Tokens `/start <token>` são assinados com `SECRET_KEY` (itsdangerous)
  e têm TTL de 10min — atacante não consegue forjar.
- `telegram_chat_id` tem `unique=True` no DB — mesmo chat não pode ser
  vinculado a 2 contas simultâneas.
