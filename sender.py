from logger import wlog
import smtplib
from email.message import EmailMessage
import os
import traceback
from database import SessionLocal, SentEmail, Lead, db_lock
import datetime

def send_email(lead_id: int, destinatario: str, asunto: str, cuerpo_html: str, new_status: str = "sent"):
    """Envía el correo y lo registra en la base de datos."""
    
    # Obtener configuración SMTP (del env por ahora)
    remitente = os.getenv("SMTP_EMAIL", "")
    password = os.getenv("SMTP_PASSWORD", "")
    smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    
    if not remitente or not password:
        return False, "Credenciales SMTP no configuradas."
        
    simulation = os.getenv("SIMULATION_MODE", "False").lower() == "true"
    
    success = False
    error_msg = ""
    
    if simulation:
        wlog(f"[SIMULACIÓN] Correo enviado a {destinatario}")
        success = True
    else:
        server = None
        try:
            server = smtplib.SMTP(smtp_server, smtp_port, timeout=15)
            server.starttls()
            server.login(remitente, password)
            
            msg = EmailMessage()
            msg["Subject"] = asunto
            msg["From"] = remitente
            msg["To"] = destinatario
            msg.set_content(cuerpo_html, subtype="html")
            
            server.send_message(msg)
            success = True
        except Exception as e:
            error_msg = str(e)
            wlog(f"      [DEBUG TRACE] {traceback.format_exc()}")
        finally:
            if server:
                try: server.quit()
                except: pass
                
    # Actualizar DB con thread-safety
    with db_lock:
        db = SessionLocal()
        try:
            lead = db.query(Lead).filter(Lead.id == lead_id).first()
            if lead:
                lead.last_attempt = datetime.datetime.utcnow()
                lead.attempt_count += 1
                
                if success:
                    if new_status is not None:
                        lead.status = new_status
                    lead.last_error = None
                    
                    sent_record = SentEmail(
                        lead_id=lead.id,
                        subject=asunto,
                        body=cuerpo_html,
                        status="sent"
                    )
                    db.add(sent_record)
                else:
                    lead.last_error = error_msg
                    if lead.attempt_count >= 3:
                        lead.status = "failed"
                        
                db.commit()
        except Exception as db_ex:
            wlog(f"❌ Error de base de datos en send_email: {db_ex}")
        finally:
            db.close()
            
    return success, error_msg
