# Como conectar o Telegram ao PoolCompras

Bot gratuito — sem custo mensal, sem templates aprovados, sem Z-API.

## Parte 1 — Criar o bot (Mateus, 1x)

1. Abra o Telegram e procure por **@BotFather**.
2. Envie `/newbot`.
3. Responda com **nome de exibição** (ex: `PoolCompras`).
4. Responda com **username** terminando em `bot` (ex: `PoolComprasBot`).
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

Sem a variável setada, o PoolCompras cai em fallback (loga no servidor).

## Parte 3 — Usuário vincula (UX automática — 3 cliques)

1. Logar no PoolCompras → **Meu perfil**.
2. Clicar **Conectar Telegram** → sistema abre o bot `@poolcomprasbot`
   no Telegram com um token de vinculação embutido.
3. No Telegram, apertar **Iniciar** (ou enviar `/start`).
4. Voltar no PoolCompras → clicar **Já dei /start, concluir** → sistema
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

## Próximos passos (opcional, futuro)

- **Webhook em produção**: quando Ademar subir VM com URL HTTPS pública,
  setar webhook (`setWebhook?url=https://.../webhook/telegram`) substitui
  o `getUpdates`. Vantagem: responde comandos em tempo real, sem precisar
  do usuário clicar "Já dei /start".
- **Comandos no bot**: `/status`, `/proximas-rodadas`, `/meu-pedido` etc.
  Requer webhook.
