from logger import wlog
import imaplib
import email
from email.header import decode_header
import os
import time
import datetime
from database import SessionLocal, Lead, Reply, db_lock
from ai_engine import classify_reply
import random
from sender import send_email
from database import get_setting

def generate_negotiation_reply(db, lead):
    availability_str = get_setting(db, "availability", "")
    opciones = [line.strip() for line in availability_str.split('\n') if line.strip()]
                    
    if len(opciones) >= 2:
        propuestas = random.sample(opciones, 2)
    else:
        propuestas = opciones if opciones else ["el próximo martes o jueves por la mañana"]
        
    cuerpo = f"""\
<html>
<body>
<p>Hola de nuevo,</p>
<p>¡Genial! Me encantaría mostrarte cómo funciona el sistema para {lead.company}.</p>
<p>¿Qué tal te vendría alguno de estos horarios para una videollamada rápida de 10 minutos?</p>
<ul>
<li>{propuestas[0]}</li>
<li>{propuestas[1] if len(propuestas) > 1 else 'Otro horario que te venga mejor'}</li>
</ul>
<p>Dime cuál prefieres y te envío el enlace a la sala.</p>
<br>
<p>Un saludo,<br>Jeremías</p>
</body>
</html>
"""
    return f"Re: Automatización para {lead.company}", cuerpo

def generate_rejection_reply(lead):
    cuerpo = f"""\
<html>
<body>
<p>¡Hola! Entiendo perfectamente, muchas gracias por responderme de todos modos.</p>
<p>Por si en algún momento de tranquilidad les da curiosidad ver cómo funciona realmente el sistema que les comentaba, les dejo este enlace con una demo interactiva de Egasis Studio:<br>
<a href="https://clinica-demo-0j13.onrender.com">https://clinica-demo-0j13.onrender.com</a><br>
<i>(Nota: Como es una versión de prueba, puede tardar unos 30 segundos en cargar la primera vez mientras se inicia el servidor).</i></p>
<p>Además de programar turnos, podemos configurar la IA para muchas otras cosas: responder a las preguntas médicas frecuentes, hacer seguimiento posterior al tratamiento, automatizar recordatorios y calificar pacientes por WhatsApp antes de llegar a la clínica, etc.</p>
<p>Les mando un saludo y estoy a la disposición por si el día de mañana necesitan algo así.</p>
<p>¡Muchos exitos!</p>
<br>
<p>Un saludo,<br>Jeremías</p>
</body>
</html>
"""
    return f"Re: Automatización para {lead.company}", cuerpo

def generate_confirmation_reply(db, lead):
    meeting_link = get_setting(db, "meeting_link", "https://meet.google.com/xxx-yyyy-zzz")
    cuerpo = f"""\
<html>
<body>
<p>¡Hola de nuevo!</p>
<p>Excelente, queda confirmada la llamada para conversar sobre {lead.company}.</p>
<p>Nos conectamos en este enlace a la hora acordada:</p>
<p><a href="{meeting_link}"><b>{meeting_link}</b></a></p>
<p>Si surge algún inconveniente, me puedes avisar respondiendo a este mismo correo.</p>
<br>
<p>Un saludo,<br>Jeremías</p>
</body>
</html>
"""
    return f"Reunión Confirmada - {lead.company}", cuerpo

def generate_info_requested_reply(db, lead):
    availability_str = get_setting(db, "availability", "")
    opciones = [line.strip() for line in availability_str.split('\n') if line.strip()]
    propuesta = opciones[0] if opciones else "el próximo martes o jueves por la mañana"
    
    cuerpo = f"""\
<html>
<body>
<p>Hola,</p>
<p>Con gusto te comento más detalles sobre cómo funciona el sistema para {lead.company}.</p>
<p><b>Egasis Studio</b> es un agente comercial autónomo con Inteligencia Artificial. Se encarga de buscar clientes ideales en Google Maps, extraer sus emails de contacto, redactar propuestas hiper-personalizadas analizando su web, y enviar los correos en frío de forma automatizada y espaciada.</p>
<p>Cuando un cliente responde con interés, el Agente Closer toma la conversación y propone horarios de tu calendario para agendar reuniones de forma 100% automática.</p>
<p>Si te da curiosidad, puedes probar una demo interactiva en vivo aquí:<br>
<a href="https://clinica-demo-0j13.onrender.com">https://clinica-demo-0j13.onrender.com</a></p>
<p>¿Qué te parece si coordinamos una llamada rápida de 10 minutos para mostrarte la plataforma en vivo? Podríamos el <b>{propuesta}</b> o en otro horario que te quede cómodo.</p>
<br>
<p>Un saludo,<br>Jeremías</p>
</body>
</html>
"""
    return f"Re: Automatización para {lead.company}", cuerpo

def is_bounce_or_autoresponder(from_email: str, subject: str, body: str) -> bool:
    from_lower = from_email.lower()
    sub_lower = subject.lower() if subject else ""
    body_lower = body.lower() if body else ""
    
    # 1. Bounces (correos rebotados)
    bounce_senders = ["mailer-daemon@", "postmaster@", "bounce@", "no-reply@", "noreply@", "mailer-daemon", "postmaster"]
    for sender in bounce_senders:
        if sender in from_lower:
            return True
            
    bounce_subjects = [
        "undelivered", "delivery status", "failure notice", "returned to sender", 
        "mail delivery failed", "failed delivery", "address not found", "user unknown",
        "could not be delivered"
    ]
    for sub in bounce_subjects:
        if sub in sub_lower:
            return True
            
    # 2. Respuestas automáticas (Auto-responders)
    auto_subjects = ["respuesta automática", "auto:", "auto-reply", "out of office", "fuera de la oficina", "vacaciones", "vacation"]
    for sub in auto_subjects:
        if sub in sub_lower:
            return True
            
    auto_bodies = [
        "gracias por contactar", "en breves momentos", "responderemos a su correo",
        "este buzón no se revisa", "esta dirección de correo no", "gracias por escribirnos",
        "no responda a este mensaje", "recibido correctamente", "correo automático",
        "out of office", "fuera de la oficina", "no disponible"
    ]
    for phrase in auto_bodies:
        if phrase in body_lower and len(body_lower) < 600:
            return True
            
    return False

def handle_rejection(lead, email):
    subj, body = generate_rejection_reply(lead)
    send_email(lead.id, email, subj, body, new_status="rechazado")

def handle_negotiation(db, lead, email):
    subj, body = generate_negotiation_reply(db, lead)
    send_email(lead.id, email, subj, body, new_status="negociando_horario")

def handle_confirmation(db, lead, email):
    subj, body = generate_confirmation_reply(db, lead)
    send_email(lead.id, email, subj, body, new_status="agendado")

def check_replies():
    """Conecta por IMAP y busca respuestas."""
    email_user = os.getenv("SMTP_EMAIL", "")
    email_pass = os.getenv("SMTP_PASSWORD", "")
    imap_server = os.getenv("IMAP_SERVER", "imap.gmail.com")
    
    if not email_user or not email_pass:
        return
        
    try:
        mail = imaplib.IMAP4_SSL(imap_server)
        mail.login(email_user, email_pass)
        mail.select("inbox")
        
        # Buscar correos de los últimos 3 días (leídos o no leídos)
        three_days_ago = (datetime.date.today() - datetime.timedelta(days=3)).strftime("%d-%b-%Y")
        status, messages = mail.search(None, f'(SINCE "{three_days_ago}")')
        
        if status != "OK" or not messages[0]:
            mail.logout()
            return
            
        for num in messages[0].split():
            status, data = mail.fetch(num, "(RFC822)")
            if status != "OK": continue
                
            for response_part in data:
                if isinstance(response_part, tuple):
                    msg = email.message_from_bytes(response_part[1])
                    subject, encoding = decode_header(msg["Subject"])[0]
                    if isinstance(subject, bytes):
                        subject = subject.decode(encoding if encoding else "utf-8")
                        
                    from_header = msg.get("From")
                    # Extraer email limpio
                    from_email = from_header
                    if "<" in from_email and ">" in from_email:
                        from_email = from_email.split("<")[1].split(">")[0]
                        
                    # Obtener el cuerpo
                    body = ""
                    if msg.is_multipart():
                        for part in msg.walk():
                            if part.get_content_type() == "text/plain":
                                try:
                                    body = part.get_payload(decode=True).decode()
                                    break
                                except: pass
                    else:
                        try:
                            body = msg.get_payload(decode=True).decode()
                        except: pass
                        
                    from_email_lower = from_email.lower().strip()
                    
                    with db_lock:
                        db = SessionLocal()
                        try:
                            lead = db.query(Lead).filter(Lead.email == from_email_lower).first()
                            if not lead and "@" in from_email_lower:
                                domain = from_email_lower.split("@")[1]
                                dominios_genericos = ["gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "icloud.com", "live.com", "msn.com"]
                                if domain not in dominios_genericos:
                                    lead = db.query(Lead).filter(Lead.email.like(f"%@{domain}")).first()
                                    
                            if lead:
                                # Si es un rebotado o auto-respuesta automática
                                if is_bounce_or_autoresponder(from_email_lower, subject, body):
                                    wlog(f"⚠️ Rebote o auto-respuesta detectada de {from_email_lower}. Marcando lead como failed.")
                                    lead.status = "failed"
                                    lead.last_error = f"Bounce o auto-respuesta: {subject}"
                                    db.commit()
                                    continue
                                    
                                wlog(f"📩 ¡Respuesta recibida de {from_email_lower}!")
                                
                                # Clasificar la respuesta (llamada a Gemini fuera del lock de escritura pero con sesión DB cerrada)
                                db.close() # Liberamos la sesión DB temporalmente para la llamada de IA
                                clsf, prio = classify_reply(body)
                                
                                # Volvemos a abrir sesión para procesar y guardar
                                db = SessionLocal()
                                # Volver a recuperar el lead en la nueva sesión
                                lead = db.query(Lead).filter(Lead.id == lead.id).first()
                                
                                reply_existe = db.query(Reply).filter(Reply.lead_id == lead.id, Reply.subject == subject).first()
                                
                                if not reply_existe:
                                    lead_id_val = lead.id
                                    company_name_val = lead.company
                                    
                                    # Extraer Aprendizaje Autónomo (sin lock pero con db cerrada es más seguro, aunque para evitar complicar abrimos/cerramos rápido)
                                    db.close()
                                    from ai_engine import extract_learning_from_reply
                                    insight = extract_learning_from_reply(body, company_name_val, clsf)
                                    
                                    db = SessionLocal()
                                    lead = db.query(Lead).filter(Lead.id == lead_id_val).first()
                                    
                                    if insight:
                                        from database import Learning
                                        new_learning = Learning(content=insight)
                                        db.add(new_learning)
                                        db.commit()
                                        wlog(f"🧠 Aprendizaje extraído: {insight}")
                                        
                                    new_reply = Reply(
                                        lead_id=lead.id,
                                        from_email=from_email_lower,
                                        subject=subject,
                                        body=body,
                                        classification=clsf,
                                        priority=prio,
                                        processed_status="pending_approval"
                                    )
                                    db.add(new_reply)
                                    db.commit()
                                    
                                    # Generar respuesta propuesta según clasificación
                                    if clsf == "interested":
                                        if lead.status == "negociando_horario":
                                            subj_out, body_out = generate_confirmation_reply(db, lead)
                                            new_reply.proposed_subject = subj_out
                                            new_reply.proposed_reply = body_out
                                            lead.status = "esperando_aprobacion"
                                            db.commit()
                                            wlog(f"   => Propuesta de Confirmación generada para aprobación manual.")
                                        else:
                                            subj_out, body_out = generate_negotiation_reply(db, lead)
                                            new_reply.proposed_subject = subj_out
                                            new_reply.proposed_reply = body_out
                                            lead.status = "esperando_aprobacion"
                                            db.commit()
                                            wlog(f"   => Propuesta de Negociación generada para aprobación manual.")
                                    elif clsf == "info_requested":
                                        subj_out, body_out = generate_info_requested_reply(db, lead)
                                        new_reply.proposed_subject = subj_out
                                        new_reply.proposed_reply = body_out
                                        lead.status = "esperando_aprobacion"
                                        db.commit()
                                        wlog(f"   => Propuesta de Información generada para aprobación manual.")
                                    elif clsf == "not_interested":
                                        subj_out, body_out = generate_rejection_reply(lead)
                                        new_reply.proposed_subject = subj_out
                                        new_reply.proposed_reply = body_out
                                        lead.status = "esperando_aprobacion"
                                        db.commit()
                                        wlog(f"   => Propuesta de Rechazo generada para aprobación manual.")
                                    elif clsf == "unsubscribe":
                                        lead.status = "do_not_contact"
                                        new_reply.processed_status = "read"
                                        db.commit()
                                        wlog(f"   => Clasificada como: unsubscribe. Marcando lead como 'do_not_contact'.")
                                    elif clsf == "spam":
                                        lead.status = "failed"
                                        new_reply.processed_status = "read"
                                        db.commit()
                                        wlog(f"   => Clasificada como: spam. Marcando lead como 'failed'.")
                                    else:
                                        lead.status = "replied"
                                        new_reply.processed_status = "read"
                                        db.commit()
                                        wlog(f"   => Clasificada como: {clsf} (Ignorada para auto-respuesta)")
                        except Exception as db_err:
                            wlog(f"❌ Error de base de datos al procesar respuesta: {db_err}")
                            try: db.rollback()
                            except: pass
                        finally:
                            db.close()
                            
        mail.logout()
    except Exception as e:
        wlog(f"Error en IMAP: {e}")

if __name__ == "__main__":
    check_replies()
