import os
import smtplib
from email.message import EmailMessage

from dotenv import load_dotenv

load_dotenv()


def _send_email(recipient: str, subject: str, body: str) -> None:
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = os.environ["MAIL_FROM"]
    message["To"] = recipient
    message.set_content(body)

    with smtplib.SMTP(os.environ["MAIL_SERVER"], int(os.getenv("MAIL_PORT", "587"))) as smtp:
        if os.getenv("MAIL_STARTTLS", "true").lower() == "true":
            smtp.starttls()
        smtp.login(os.environ["MAIL_USERNAME"], os.environ["MAIL_PASSWORD"])
        smtp.send_message(message)


def send_two_factor_code(recipient: str, code: str) -> None:
    # As credenciais ficam somente no ambiente; o código é usado apenas para
    # montar a mensagem e nunca é persistido ou registrado em logs.
    _send_email(
        recipient,
        "Código de verificação - Hemo Connect",
        "Seu código de verificação do Hemo Connect é:\n\n"
        f"{code}\n\n"
        "Este código é válido por 5 minutos.\n"
        "Não compartilhe este código.",
    )


def send_password_reset_link(recipient: str, reset_url: str) -> None:
    _send_email(
        recipient,
        "Redefinição de senha - Hemo Connect",
        "Você solicitou a redefinição da sua senha no Hemo Connect.\n\n"
        f"Clique no link abaixo para criar uma nova senha:\n{reset_url}\n\n"
        "Este link expira em 15 minutos.\n"
        "Se você não solicitou essa alteração, ignore este e-mail.",
    )