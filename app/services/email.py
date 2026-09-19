import os
import logging
from email.utils import parseaddr

import httpx


logger = logging.getLogger(__name__)


def _send_email(recipient: str, subject: str, body: str) -> None:
    # O provedor e chamado somente pelo backend; a chave nunca participa do payload ou dos logs.
    api_key = os.environ.get("BREVO_API_KEY")
    if not api_key:
        raise RuntimeError("BREVO_API_KEY não está configurada")

    sender_value = os.environ.get("MAIL_FROM")
    if not sender_value:
        raise RuntimeError("MAIL_FROM não está configurada")

    sender_name = os.environ.get("MAIL_FROM_NAME", "Hemo Connect")
    sender_email = parseaddr(sender_value)[1] or sender_value.strip()
    if not sender_email:
        raise RuntimeError("MAIL_FROM não contém um endereço válido")

    payload = {
        "sender": {"name": sender_name, "email": sender_email},
        "to": [{"email": recipient}],
        "subject": subject,
        "textContent": body,
    }
    try:
        # A API HTTPS evita SMTP e o timeout impede que login/reset fiquem pendurados indefinidamente.
        response = httpx.post(
            "https://api.brevo.com/v3/smtp/email",
            headers={
                "accept": "application/json",
                "api-key": api_key,
                "content-type": "application/json",
            },
            json=payload,
            timeout=10.0,
        )
        response.raise_for_status()
    except httpx.HTTPError:
        # A excecao retorna ao fluxo de autenticacao, que remove desafios/tokens não entregues.
        logger.warning("Falha no envio do e-mail | status=falha | recipient=%s", recipient)
        raise
    except Exception:
        logger.warning("Falha no envio do e-mail | status=falha | recipient=%s", recipient)
        raise
    logger.info("E-mail enviado | status=sucesso | recipient=%s", recipient)


def send_two_factor_code(recipient: str, code: str) -> None:
    # O código aparece apenas no corpo entregue ao provedor e não é registrado pelo logger.
    _send_email(
        recipient,
        "Código de verificação - Hemo Connect",
        "Seu código de verificação do Hemo Connect é:\n\n"
        f"{code}\n\n"
        "Este código é válido por 5 minutos.\n"
        "Não compartilhe este código."
    )


def send_password_reset_email(recipient: str, reset_url: str) -> None:
    # O link segue no corpo do e-mail, mas nunca é incluído nas mensagens operacionais.
    _send_email(
        recipient,
        "Redefinição de senha - Hemo Connect",
        "Recebemos uma solicitação para redefinir sua senha no Hemo Connect.\n\n"
        f"Acesse o link para criar uma nova senha:\n{reset_url}\n\n"
        "Este link é válido por 15 minutos e pode ser utilizado uma única vez.\n"
        "Se você não solicitou a redefinição, ignore esta mensagem."
    )