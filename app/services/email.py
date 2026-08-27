import os
import smtplib
from email.message import EmailMessage

from dotenv import load_dotenv

load_dotenv()


def send_two_factor_code(recipient: str, code: str) -> None:
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