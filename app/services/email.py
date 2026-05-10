"""Helper de envio de e-mail via SMTP (stdlib — sem dependencia nova).

Configuracao via variaveis de ambiente (todas opcionais — se SMTP_HOST
nao estiver definido, `enviar_email()` retorna False sem crashar):

    SMTP_HOST       host do servidor SMTP (ex: smtp.gmail.com)
    SMTP_PORT       porta (default 587 com STARTTLS, 465 com SSL implicito)
    SMTP_USER       login (geralmente o proprio e-mail)
    SMTP_PASSWORD   senha ou app password
    SMTP_FROM       remetente exibido (ex: "Aggron <contato@aggron.com.br>")
    SMTP_USE_SSL    "true" pra SMTPS implicito (porta 465). Default: false
                    (usa STARTTLS na porta 587).

Exemplo .env (Gmail/Workspace):
    SMTP_HOST=smtp.gmail.com
    SMTP_PORT=587
    SMTP_USER=contato@aggron.com.br
    SMTP_PASSWORD=app-password-de-16-chars
    SMTP_FROM=Aggron <contato@aggron.com.br>

LGPD: nao loga corpo do e-mail. So loga sucesso/falha + email mascarado.
"""
import logging
import os
import smtplib
import ssl
from email.message import EmailMessage

from app.services.pii import mask_email

logger = logging.getLogger(__name__)

_TIMEOUT_SEG = 10


def smtp_configurado() -> bool:
    """True se SMTP_HOST + SMTP_USER + SMTP_PASSWORD estao todos definidos."""
    return bool(
        os.environ.get("SMTP_HOST")
        and os.environ.get("SMTP_USER")
        and os.environ.get("SMTP_PASSWORD")
    )


def enviar_email(para: str, assunto: str, corpo_texto: str,
                 corpo_html: str | None = None) -> bool:
    """Envia e-mail via SMTP. Retorna True se entregue ao servidor SMTP
    (nao garante entrega final ao destinatario), False em qualquer falha.

    Falhas sao logadas com email mascarado (LGPD-friendly) e nao
    propagam excecao — caller decide o que fazer.
    """
    if not smtp_configurado():
        logger.info("SMTP nao configurado — email para %s ignorado", mask_email(para))
        return False

    host = os.environ["SMTP_HOST"]
    port = int(os.environ.get("SMTP_PORT", "587"))
    user = os.environ["SMTP_USER"]
    password = os.environ["SMTP_PASSWORD"]
    remetente = os.environ.get("SMTP_FROM", user)
    usar_ssl = os.environ.get("SMTP_USE_SSL", "false").lower() == "true"

    msg = EmailMessage()
    msg["From"] = remetente
    msg["To"] = para
    msg["Subject"] = assunto
    msg.set_content(corpo_texto)
    if corpo_html:
        msg.add_alternative(corpo_html, subtype="html")

    try:
        ctx = ssl.create_default_context()
        if usar_ssl:
            with smtplib.SMTP_SSL(host, port, context=ctx, timeout=_TIMEOUT_SEG) as s:
                s.login(user, password)
                s.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=_TIMEOUT_SEG) as s:
                s.ehlo()
                s.starttls(context=ctx)
                s.ehlo()
                s.login(user, password)
                s.send_message(msg)
        logger.info("EMAIL_OK para=%s assunto=%r", mask_email(para), assunto)
        return True
    except smtplib.SMTPException as e:
        logger.warning("EMAIL_SMTP_FAIL para=%s erro=%s",
                       mask_email(para), type(e).__name__)
        return False
    except (OSError, ssl.SSLError) as e:
        logger.warning("EMAIL_NET_FAIL para=%s erro=%s",
                       mask_email(para), type(e).__name__)
        return False
