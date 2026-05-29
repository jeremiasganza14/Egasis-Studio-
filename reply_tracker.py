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
Hola de nuevo,

¡Genial! Me encantaría mostrarte cómo funciona el sistema para {lead.company}.

¿Qué tal te vendría alguno de estos horarios para una videollamada rápida de 10 minutos?
- {propuestas[0]}
- {propuestas[1] if len(propuestas) > 1 else 'Otro horario que te venga mejor'}

Dime cuál prefieres y te envío el enlace a la sala.

Un saludo,
Jeremías
"""
    return f"Re: Automatización para {lead.company}", cuerpo

def generate_rejection_reply(lead):
    cuerpo = f"""\
¡Hola! Entiendo perfectamente, muchas gracias por responderme de todos modos.

Por si en algún momento de tranquilidad les da curiosidad ver cómo funciona realmente el sistema que les comentaba, les dejo este enlace con una demo interactiva de Egasis Studio:
https://clinica-demo-0j13.onrender.com
(Nota: Como es una versión de prueba, puede tardar unos 30 segundos en cargar la primera vez mientras se inicia el servidor).

Además de programar turnos, podemos configurar la IA para muchas otras cosas: responder a las preguntas médicas frecuentes, hacer seguimiento posterior al tratamiento, automatizar recordatorios y calificar pacientes por WhatsApp antes de llegar a la clínica, etc.

Les mando un saludo y estoy a la disposición por si el día de mañana necesitan algo así.

¡Muchos exitos!

Un saludo,
Jeremías
"""
    return f"Re: Automatización para {lead.company}", cuerpo

def generate_confirmation_reply(db, lead):
    meeting_link = get_setting(db, "meeting_link", "https://meet.google.com/xxx-yyyy-zzz")
    cuerpo = f"""\
¡Hola de nuevo!

Excelente, queda confirmada la llamada para conversar sobre {lead.company}.

Nos conectamos en este enlace a la hora acordada:
{meeting_link}

Si surge algún inconveniente, me puedes avisar respondiendo a este mismo correo.

Un saludo,
Jeremías
"""
    return f"Reunión Confirmada - {lead.company}", cuerpo

def generate_info_requested_reply(db, lead):
    availability_str = get_setting(db, "availability", "")
    opciones = [line.strip() for line in availability_str.split('\n') if line.strip()]
    propuesta = opciones[0] if opciones else "el próximo martes o jueves por la mañana"
    
    cuerpo = f"""\
Hola,

Con gusto te comento más detalles sobre cómo funciona el sistema para {lead.company}.

Egasis Studio es un agente comercial autónomo con Inteligencia Artificial. Se encarga de buscar clientes ideales en Google Maps, extraer sus emails de contacto, redactar propuestas hiper-personalizadas analizando su web, y enviar los correos en frío de forma automatizada y espaciada.

Cuando un cliente responde con interés, el Agente Closer toma la conversación y propone horarios de tu calendario para agendar reuniones de forma 100% automática.

Si te da curiosidad, puedes probar una demo interactiva en vivo aquí:
https://clinica-demo-0j13.onrender.com

¿Qué te parece si coordinamos una llamada rápida de 10 minutos para mostrarte la plataforma en vivo? Podríamos el {propuesta} o en otro horario que te quede cómodo.

Un saludo,
Jeremías
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
    db = SessionLocal()
    email_user = get_setting(db, "smtp_email", os.getenv("SMTP_EMAIL", ""))
    email_pass = get_setting(db, "smtp_password", os.getenv("SMTP_PASSWORD", ""))
    imap_server = os.getenv("IMAP_SERVER", "imap.gmail.com")
    db.close()
    
    if not email_user or not email_pass:
        return
        
    try:
        mail = imaplib.IMAP4_SSL(imap_server)
        mail.login(email_user, email_pass)
        mail.select("inbox")
        
        # Buscar correos de los últimos 3 días (es seguro y ahora será ultrarrápido)
        three_days_ago = (datetime.date.today() - datetime.timedelta(days=3)).strftime("%d-%b-%Y")
        status, messages = mail.search(None, f'(SINCE "{three_days_ago}")')
        
        if status != "OK" or not messages[0]:
            print(f"DEBUG IMAP: No messages found or search failed. Status: {status}, Messages: {messages}")
            mail.logout()
            return
            
        all_ids = messages[0].split()
            
        for num in all_ids:
            # FASE 1: Extraer solo los encabezados del correo (ultrarrápido, no marca como leído)
            status, header_data = mail.fetch(num, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT)])")
            if status != "OK": continue
                
            from_email = ""
            subject = ""
            
            for response_part in header_data:
                if isinstance(response_part, tuple):
                    msg = email.message_from_bytes(response_part[1])
                    
                    # Asunto
                    subj_header = msg.get("Subject")
                    if subj_header:
                        try:
                            subject, encoding = decode_header(subj_header)[0]
                            if isinstance(subject, bytes):
                                subject = subject.decode(encoding if encoding else "utf-8")
                        except: pass
                        
                    # Remitente
                    from_header = msg.get("From")
                    if from_header:
                        from_email = from_header
                        if "<" in from_email and ">" in from_email:
                            from_email = from_email.split("<")[1].split(">")[0]
                            
            if not from_email: continue
            from_email_lower = from_email.lower().strip()
            print(f"DEBUG IMAP: Found email from {from_email_lower}")
            
            with db_lock:
                db = SessionLocal()
                try:
                    # Comprobar si el remitente está en nuestra base de Leads
                    lead = db.query(Lead).filter(Lead.email == from_email_lower).first()
                    if not lead and "@" in from_email_lower:
                        domain = from_email_lower.split("@")[1]
                        dominios_genericos = ["gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "icloud.com", "live.com", "msn.com"]
                        if domain not in dominios_genericos:
                            lead = db.query(Lead).filter(Lead.email.like(f"%@{domain}")).first()
                            
                    if lead:
                        # Verificar inmediatamente si ya procesamos este correo para no volver a descargarlo
                        reply_existe = db.query(Reply).filter(Reply.lead_id == lead.id, Reply.subject == subject).first()
                        if reply_existe:
                            continue
                            
                        # FASE 2: Como es un lead nuevo que respondió, AHORA descargamos el cuerpo pesado del correo
                        status_full, full_data = mail.fetch(num, "(RFC822)")
                        if status_full != "OK": continue
                        
                        body = ""
                        for r_part in full_data:
                            if isinstance(r_part, tuple):
                                full_msg = email.message_from_bytes(r_part[1])
                                if full_msg.is_multipart():
                                    for part in full_msg.walk():
                                        if part.get_content_type() == "text/plain":
                                            try:
                                                body = part.get_payload(decode=True).decode()
                                                break
                                            except: pass
                                else:
                                    try:
                                        body = full_msg.get_payload(decode=True).decode()
                                    except: pass
                                    
                                # Dejamos que la IA clasifique todo (incluso bounces o auto-respuestas) 
                                # para evitar falsos positivos y así guardarlo en BD evitando bucles infinitos.
                                    
                                wlog(f"📩 ¡Respuesta recibida de {from_email_lower}!")
                                
                                # Clasificar la respuesta (llamada a Gemini fuera del lock de escritura pero con sesión DB cerrada)
                                db.close() # Liberamos la sesión DB temporalmente para la llamada de IA
                                clsf, prio = classify_reply(body)
                                
                                # Volvemos a abrir sesión para procesar y guardar
                                db = SessionLocal()
                                # Volver a recuperar el lead en la nueva sesión
                                lead = db.query(Lead).filter(Lead.id == lead.id).first()
                                
                                if True: # Mantener la indentación del bloque siguiente
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
                                    
                                    from ai_engine import generate_custom_reply_draft
                                    if clsf in ["interested", "info_requested", "unclassified", "not_interested"]:
                                        avail = get_setting(db, "availability", "")
                                        ai_body = generate_custom_reply_draft(body, lead.company, clsf, avail)
                                        
                                        if ai_body:
                                            new_reply.proposed_subject = f"Re: {subject}"
                                            new_reply.proposed_reply = ai_body
                                            lead.status = "esperando_aprobacion"
                                            db.commit()
                                            wlog(f"   => Borrador de respuesta inteligente (IA) generado para aprobación.")
                                        else:
                                            # Fallback
                                            if clsf == "interested":
                                                body_lower = body.lower()
                                                if any(word in body_lower for word in ["lunes", "martes", "miércoles", "miercoles", "jueves", "viernes", "sábado", "sabado", "domingo", "mañana", "tarde", "perfecto", "genial", ":00", " a las "]):
                                                    subj_out, body_out = generate_confirmation_reply(db, lead)
                                                else:
                                                    subj_out, body_out = generate_negotiation_reply(db, lead)
                                            elif clsf == "info_requested":
                                                subj_out, body_out = generate_info_requested_reply(db, lead)
                                            elif clsf == "not_interested":
                                                subj_out, body_out = generate_rejection_reply(lead)
                                            else:
                                                subj_out, body_out = f"Re: {subject}", "¡Hola! Recibimos tu respuesta. ¿En qué más podemos ayudarte?"
                                                
                                            if subj_out:
                                                new_reply.proposed_subject = subj_out
                                                new_reply.proposed_reply = body_out
                                                lead.status = "esperando_aprobacion"
                                                db.commit()
                                                wlog(f"   => Propuesta estándar generada para aprobación manual.")
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
