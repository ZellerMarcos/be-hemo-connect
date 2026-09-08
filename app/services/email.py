import os
import logging

import resend


logger = logging.getLogger(__name__)


def _send_email(recipient: str, subject: str, body: str) -> None:
    api_key = os.environ.get("RESEND_API_KEY")
    if not api_key:
        raise RuntimeError("RESEND_API_KEY não está configurada")

    sender = os.environ.get("MAIL_FROM")
    if not sender:
        raise RuntimeError("MAIL_FROM não está configurada")

    resend.api_key = api_key
    try:
        resend.Emails.send(
            {
                "from": sender,
                "to": [recipient],
                "subject": subject,
                "text": body,
            }
        )
    except Exception:
        logger.warning("Falha no envio do e-mail | status=falha | recipient=%s", recipient)
        raise
    logger.info("E-mail enviado | status=sucesso | recipient=%s", recipient)


def send_two_factor_code(recipient: str, code: str) -> None:
    _send_email(
        recipient,
        "Código de verificação - Hemo Connect",
        "Seu código de verificação do Hemo Connect é:\n\n"
        f"{code}\n\n"
        "Este código é válido por 5 minutos.\n"
        "Não compartilhe este código."
    )


def send_password_reset_email(recipient: str, reset_url: str) -> None:
    _send_email(
        recipient,
        "Redefinição de senha - Hemo Connect",
        "Recebemos uma solicitação para redefinir sua senha no Hemo Connect.\n\n"
        f"Acesse o link para criar uma nova senha:\n{reset_url}\n\n"
        "Este link é válido por 15 minutos e pode ser utilizado uma única vez.\n"
        "Se você não solicitou a redefinição, ignore esta mensagem."
    )