import os
import smtplib
from email.message import EmailMessage
from dotenv import load_dotenv

load_dotenv()
remitente = os.getenv("SMTP_EMAIL", "")
password = os.getenv("SMTP_PASSWORD", "")
smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
smtp_port = int(os.getenv("SMTP_PORT", "587"))

print(f"Testing with remitente: {remitente}")

try:
    server = smtplib.SMTP(smtp_server, smtp_port, timeout=15)
    server.starttls()
    server.login(remitente, password)

    msg = EmailMessage()
    msg["Subject"] = "Una idea para Clínica Robega | Medicina Estética"
    msg["From"] = remitente
    msg["To"] = remitente
    cuerpo_html = """<html><body><p>Hola <b>Equipo</b>,</p><p>Estuve revisando la web de <b>Clínica Robega | Medicina Estética</b> y me pareció muy interesante el trabajo que realizan.</p><p>Me dedico a construir <b>Sistemas de Inteligencia Artificial Privados</b> para empresas. En lugar de pagar chatbots básicos mensuales que fallan, construyo el cerebro directamente en sus propios servidores para que sean dueños de la tecnología.</p></body></html>"""
    msg.set_content(cuerpo_html, subtype="html")

    server.send_message(msg)
    print("Success send_message")
    server.quit()
except Exception as e:
    import traceback
    traceback.print_exc()

