import sys
import os
from database import SessionLocal, Lead, Reply, Learning, get_setting, db_lock
from ai_engine import classify_reply, extract_learning_from_reply
from reply_tracker import handle_negotiation, handle_rejection, handle_confirmation
from logger import wlog

def simulate_customer_reply(target_email: str, company_name: str, client_name: str, message_body: str):
    """
    Simula la llegada de un correo de un cliente específico.
    Ejecuta toda la lógica de IA: clasificación, extracción de aprendizaje,
    actualización de base de datos y envío de correos automáticos.
    """
    wlog(f"\n🧪 --- INICIANDO SIMULACIÓN DE RESPUESTA ---")
    wlog(f"Cliente: {client_name} ({company_name}) <{target_email}>")
    wlog(f"Mensaje Simulado:\n\"\"\"\n{message_body}\n\"\"\"")
    
    db = SessionLocal()
    with db_lock:
        try:
            # 1. Crear o buscar el lead en la base de datos
            lead = db.query(Lead).filter(Lead.email == target_email.lower().strip()).first()
            if not lead:
                wlog(f"➕ Creando lead de prueba para {target_email}...")
                lead = Lead(
                    email=target_email.lower().strip(),
                    company=company_name,
                    name=client_name,
                    status="sent",  # Simula que ya le mandamos el primer correo
                    source="manual"
                )
                db.add(lead)
                db.commit()
                db.refresh(lead)
            
            # 2. Clasificar el mensaje usando Gemini (cerrando sesión temporalmente)
            db.close()
            wlog("🧠 Clasificando mensaje con Gemini...")
            clsf, prio = classify_reply(message_body)
            wlog(f"   => Clasificación: {clsf} | Prioridad: {prio}")
            
            db = SessionLocal()
            lead = db.query(Lead).filter(Lead.id == lead.id).first()
            
            # 3. Guardar la respuesta en la base de datos
            subject = f"Re: Automatización para {lead.company}"
            new_reply = Reply(
                lead_id=lead.id,
                from_email=lead.email,
                subject=subject,
                body=message_body,
                classification=clsf,
                priority=prio,
                processed_status="unread"
            )
            db.add(new_reply)
            db.commit()
            wlog("💾 Respuesta guardada en la base de datos.")
            
            lead_id = lead.id
            company_name_val = lead.company
            new_reply_id = new_reply.id
            
            # 4. Extraer aprendizaje autónomo con Gemini (cerrando sesión temporalmente)
            db.close()
            wlog("🧠 Extrayendo aprendizaje de la respuesta...")
            insight = extract_learning_from_reply(message_body, company_name_val, clsf)
            
            db = SessionLocal()
            lead = db.query(Lead).filter(Lead.id == lead_id).first()
            new_reply = db.query(Reply).filter(Reply.id == new_reply_id).first()
            if insight:
                new_learning = Learning(content=insight)
                db.add(new_learning)
                db.commit()
                wlog(f"   => 💡 Bitácora actualizada: {insight}")
                
            # 5. Ejecutar la máquina de estados y enviar respuesta automática
            wlog("⚙️ Evaluando máquina de estados del lead...")
            if clsf == "interested":
                if lead.status == "negociando_horario":
                    wlog("📅 El cliente confirmó la fecha. Pasando a 'agendado' y enviando confirmación...")
                    lead.status = "agendado"
                    db.commit()
                    handle_confirmation(db, lead, lead.email)
                else:
                    wlog("📩 El cliente muestra interés inicial. Pasando a 'negociando_horario' y proponiendo fechas...")
                    lead.status = "negociando_horario"
                    db.commit()
                    handle_negotiation(db, lead, lead.email)
            elif clsf == "info_requested":
                wlog("📩 El cliente solicita información. Pasando a 'esperando_aprobacion' y proponiendo info...")
                lead.status = "esperando_aprobacion"
                db.commit()
                from reply_tracker import generate_info_requested_reply
                subj, body = generate_info_requested_reply(db, lead)
                new_reply.proposed_subject = subj
                new_reply.proposed_reply = body
                new_reply.processed_status = "pending_approval"
                db.commit()
            elif clsf == "not_interested":
                wlog("🛑 El cliente rechazó. Pasando a 'rechazado' y enviando email de cortesía con demo...")
                lead.status = "rechazado"
                db.commit()
                handle_rejection(lead, lead.email)
            elif clsf == "unsubscribe":
                wlog("🛑 El cliente solicitó baja. Pasando a 'do_not_contact' y no enviando ningún correo...")
                lead.status = "do_not_contact"
                db.commit()
            elif clsf == "spam":
                wlog("⚠️ Correo clasificado como spam. Pasando a 'failed'...")
                lead.status = "failed"
                db.commit()
            else:
                wlog("⚠️ Mensaje no concluyente o de otro tipo. Marcando como respondido para revisión manual.")
                lead.status = "replied"
                db.commit()
                
            wlog("🎉 --- SIMULACIÓN FINALIZADA CON ÉXITO ---")
            wlog("Revisa el Dashboard y tu casilla de correo para ver el resultado en vivo.")
            
        except Exception as e:
            wlog(f"❌ Error en la simulación: {e}")
        finally:
            db.close()

if __name__ == "__main__":
    # Configuración por defecto
    # Si quieres recibir los emails de prueba reales, pon tu email personal aquí.
    DEFAULT_TEST_EMAIL = "jeremiasganza14@gmail.com" 
    
    print("\n--- SIMULADOR DE AGENCIA AUTÓNOMA ---")
    print("1. Simular respuesta POSITIVA (Interés inicial)")
    print("2. Simular respuesta POSITIVA (Confirmando horario)")
    print("3. Simular respuesta NEGATIVA (Rechazo)")
    
    opcion = input("\nElige una opción (1-3): ").strip()
    
    if opcion == "1":
        simulate_customer_reply(
            target_email=DEFAULT_TEST_EMAIL,
            company_name="Clínica Dental Estética Test",
            client_name="Dr. Juan Pérez",
            message_body="Hola Jeremías, me interesa lo del cerebro de IA. Me gustaría ver cómo funciona exactamente y agendar una videollamada corta. Avísame qué días puedes."
        )
    elif opcion == "2":
        # Para esta prueba, primero forzamos el estado a negociando_horario
        db = SessionLocal()
        lead = db.query(Lead).filter(Lead.email == DEFAULT_TEST_EMAIL).first()
        if lead:
            lead.status = "negociando_horario"
            db.commit()
        db.close()
        
        simulate_customer_reply(
            target_email=DEFAULT_TEST_EMAIL,
            company_name="Clínica Dental Estética Test",
            client_name="Dr. Juan Pérez",
            message_body="Hola, perfecto, me viene bien el próximo miércoles a las 11:30 AM de Argentina. Nos vemos ahí."
        )
    elif opcion == "3":
        simulate_customer_reply(
            target_email=DEFAULT_TEST_EMAIL,
            company_name="Clínica Dental Estética Test",
            client_name="Dr. Juan Pérez",
            message_body="Gracias Jeremías, pero por el momento no estamos interesados en automatizar nada ni meter Inteligencia Artificial. Saludos."
        )
    else:
        print("Opción no válida.")
