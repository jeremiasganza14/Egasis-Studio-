import traceback
from email.message import EmailMessage

msg = EmailMessage()
msg["Subject"] = "Una idea para Clínica Robega | Medicina Estética"
msg["From"] = "jereganza@gmail.com"
msg["To"] = "info@clinicarobega.com"

cuerpo_html = """<html><body><p>Hola <b>Equipo</b>,</p><p>Estuve revisando la web de <b>Clínica Robega | Medicina Estética</b> y me pareció muy interesante el trabajo que realizan.</p><p>Me dedico a construir <b>Sistemas de Inteligencia Artificial Privados</b> para empresas. En lugar de pagar chatbots básicos mensuales que fallan, construyo el cerebro directamente en sus propios servidores para que sean dueños de la tecnología.</p></body></html>"""

try:
    msg.set_content(cuerpo_html, subtype="html")
    msg.as_string()
    msg.as_bytes()
    print("No errors in msg generation")
except Exception as e:
    print("Error during msg generation:")
    traceback.print_exc()

