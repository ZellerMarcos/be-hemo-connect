import os
import smtplib
from email.message import EmailMessage

from dotenv import load_dotenv

load_dotenv()


def send_two_factor_code(recipient: str, code: str) -> None:
    # As credenciais ficam somente no ambiente; o código é usado apenas para
    # montar a mensagem e nunca é persistido ou registrado em logs.
    message = EmailMessage()
    message["Subject"] = "Código de verificação - Hemo Connect"
    message["From"] = os.environ["MAIL_FROM"]
    message["To"] = recipient
    message.set_content(
        "Seu código de verificação do Hemo Connect é:\n\n"
        f"{code}\n\n"
        "Este código é válido por 5 minutos.\n"
        "Não compartilhe este código."
    )
    with smtplib.SMTP(os.environ["MAIL_SERVER"], int(os.getenv("MAIL_PORT", "587"))) as smtp:
        if os.getenv("MAIL_STARTTLS", "true").lower() == "true":
            smtp.starttls()
        smtp.login(os.environ["MAIL_USERNAME"], os.environ["MAIL_PASSWORD"])
        smtp.send_message(message)


def send_password_reset_link(recipient: str, reset_url: str) -> None:
    # O link contém um token temporário e é enviado somente para o e-mail cadastrado.
    message = EmailMessage()
    message["Subject"] = "Redefinição de senha - Hemo Connect"
    message["From"] = os.environ["MAIL_FROM"]
    message["To"] = recipient
    message.set_content(
        "Recebemos uma solicitação para redefinir sua senha no Hemo Connect.\n\n"
        f"Acesse o link para criar uma nova senha:\n{reset_url}\n\n"
        "Este link é válido por 15 minutos e pode ser utilizado uma única vez.\n"
        "Se você não solicitou a redefinição, ignore esta mensagem."
    )
    # Reutiliza as mesmas configurações SMTP do envio do código 2FA.
    with smtplib.SMTP(os.environ["MAIL_SERVER"], int(os.getenv("MAIL_PORT", "587"))) as smtp:
        if os.getenv("MAIL_STARTTLS", "true").lower() == "true":
            smtp.starttls()
        smtp.login(os.environ["MAIL_USERNAME"], os.environ["MAIL_PASSWORD"])
        smtp.send_message(message)