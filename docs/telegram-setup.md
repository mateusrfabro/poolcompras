# Como conectar o Telegram ao PoolCompras

Bot gratuito — sem custo mensal, sem templates aprovados, sem Z-API.

## Parte 1 — Criar o bot (Mateus faz 1x)

1. Abra o Telegram e procure por **@BotFather**.
2. Envie `/newbot`.
3. Responda com **nome de exibição** (ex: `PoolCompras`).
4. Responda com **username** — precisa terminar em `bot`. Ex: `PoolComprasBot`.
   Se já estiver em uso, tente `PoolComprasLondrinaBot` ou similar.
5. O BotFather vai mandar uma mensagem com o **token** no formato
   `123456789:ABC-DEF1234ghIkl-zyx57W2v1u123ew11` — **guarde esse token**.
6. (Opcional mas recomendado) ainda com o BotFather, envie `/setdescription`,
   escolha seu bot e cole uma descrição tipo:
   > Notificações do PoolCompras — central de compras cooperativa de Londrina.
   > Envie /start para receber seu código de vinculação.

## Parte 2 — Configurar o token no servidor

No ambiente onde o PoolCompras roda (dev local ou VM do Ademar), adicione a
variável de ambiente **`TELEGRAM_BOT_TOKEN`**:

**Local (Windows/Bash):**
```bash
export TELEGRAM_BOT_TOKEN="123456789:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"
python run.py
```

**Prod (.env ou systemd):**
```
TELEGRAM_BOT_TOKEN=123456789:ABC-...
```

Sem essa variável setada, o PoolCompras cai no fallback silencioso (loga a
notificação) — nada quebra.

## Parte 3 — Cada usuário vincula seu chat_id

Cada admin/lanchonete/fornecedor precisa fazer isso UMA vez.

### Forma simples (recomendada — funciona já)

1. No Telegram, procure por **@userinfobot** (bot público do Telegram).
2. Envie `/start`. Ele responde com:
   ```
   Id: 987654321
   First: Seu Nome
   ...
   ```
3. Copie o número de **Id**.
4. Entre no PoolCompras → **Meu perfil** → campo **"Seu chat_id do Telegram"**
   → cole o número → **Salvar alterações**.
5. Procure o bot do PoolCompras (ex: `@PoolComprasBot`) e envie qualquer
   mensagem (ex: `oi`). Isso **abre a conversa** — o Telegram só entrega
   mensagens de bots pra quem já iniciou conversa.

A partir daí, você recebe notificações de: reset de senha, propostas
aprovadas/devolvidas, pagamentos confirmados, entregas informadas.

### Forma nativa (quando tiver VM pública)

Quando o Ademar subir em produção com URL pública (HTTPS):

1. Configurar webhook: `curl "https://api.telegram.org/bot<TOKEN>/setWebhook?url=https://poolcompras.exemplo/webhook/telegram"`
2. Adicionar rota Flask que recebe `/start` e responde automaticamente com
   o chat_id do próprio Telegram update. (Não implementado ainda — a via
   `@userinfobot` supre bem até lá.)

## Parte 4 — Validar que chegou

1. Com chat_id salvo no perfil e `TELEGRAM_BOT_TOKEN` setado no servidor,
   faça logout e clique em **"Esqueci minha senha"**.
2. Informe seu e-mail cadastrado.
3. Em poucos segundos o bot envia no Telegram o link de recuperação.

Se não chegou:
- Você abriu conversa com o bot? (Telegram bloqueia entrega inicial.)
- Log do servidor mostra `TELEGRAM_OK usuario=X`? Se sim, é sua conta Telegram.
- Log mostra `TELEGRAM_FAIL ... 403 Forbidden`? Você bloqueou o bot ou não
  iniciou a conversa.
- Log mostra `NOTIF_FALLBACK`? Token ou chat_id não estão configurados.

## Eventos que notificam hoje

| Evento | Quem recebe |
|---|---|
| Reset de senha solicitado | Dono do e-mail |
| Pedido aprovado / devolvido / reprovado | Lanchonete |
| Cotação final aprovada / devolvida | Fornecedor |
| Comprovante de pagamento enviado | Fornecedor(es) vencedor(es) |
| Pagamento confirmado pelo fornecedor | Lanchonete |
| Entrega informada pelo fornecedor | Lanchonete |

Futuro: proposta consolidada disponível pra aceite, alertas de deadline,
avaliações recebidas.
