from logger import wlog
import time
import random
import datetime
import os
import threading
from database import SessionLocal, Lead, Setting, SentEmail, get_setting, set_setting, db_lock
from sender import send_email
from ai_engine import generate_ai_variant
from reply_tracker import check_replies

# Estado global del bot
is_running = False
scheduler_thread = None

CUERPO_HTML_BASE = """\
<html>
  <body>
    <p>{Hola|Estimado|Qué tal} <b>{Nombre}</b>,</p>
    <p>Estuve revisando la web de <b>{Empresa}</b> y me pareció muy interesante el trabajo que realizan.</p>
    <p>Somos <b>Egasis Studio</b> y ayudamos a agencias y clínicas a escalar mediante un <b>Sistema de Prospección Autónomo</b>. Construimos un software que busca clientes ideales, analiza sus páginas web, extrae correos y les envía propuestas personalizadas mediante IA, 100% en piloto automático.</p>
    <p>El sistema se conecta a WhatsApp, atiende clientes 24/7 y agenda reuniones de forma automática. Además, podemos personalizar las respuestas exactamente a sus necesidades.</p>
    <p>¿Tendrían 10 minutos para que les muestre cómo funcionaría esto exactamente para ustedes?</p>
    <br>
    <p>Un saludo,<br>Jeremías</p>
  </body>
</html>
"""

def bot_loop():
    global is_running
    wlog("[CLOSER] 🚀 Scheduler de prospección y seguimiento iniciado.")
    
    last_imap_check = 0
    
    while is_running:
        try:
            # 1. Comprobar si está activo en la DB & horario & límite (atómico y rápido)
            with db_lock:
                db = SessionLocal()
                status = get_setting(db, "bot_status", "stopped")
                work_start = int(get_setting(db, "work_hour_start", os.getenv("WORK_HOUR_START", "8")))
                work_end = int(get_setting(db, "work_hour_end", os.getenv("WORK_HOUR_END", "18")))
                daily_limit = int(get_setting(db, "daily_limit", os.getenv("DAILY_LIMIT", "80")))
                
                today = datetime.date.today()
                # Contar correos enviados hoy
                sent_today = db.query(SentEmail).filter(
                    SentEmail.sent_at >= datetime.datetime(today.year, today.month, today.day)
                ).count()
                
                # Buscar próximo lead pendiente
                lead = db.query(Lead).filter(Lead.status == "pending").first()
                
                search_queue_str = get_setting(db, "search_queue", "")
                current_idx = int(get_setting(db, "current_queue_index", "0"))
                db.close()
                
            if status != "running":
                is_running = False
                wlog("[SYSTEM] 🛑 Bot detenido desde configuración.")
                break
                
            # 2. Comprobar horario de trabajo
            current_hour = datetime.datetime.now().hour
            if current_hour < work_start or current_hour >= work_end:
                wlog(f"[CLOSER] ⏳ Fuera del horario laboral ({work_start}:00 - {work_end}:00). En espera...")
                time.sleep(600)
                continue
                
            # 3. Comprobar límite diario
            if sent_today >= daily_limit:
                wlog(f"[CLOSER] ✅ Límite diario alcanzado ({sent_today}/{daily_limit}). Durmiendo hasta mañana...")
                time.sleep(3600)
                continue
                
            # 4. Chequeo IMAP (cada 15 minutos aprox, no bloquea BD)
            if time.time() - last_imap_check > 900:
                wlog("[CLOSER] 🔍 Revisando respuestas recibidas en Gmail (IMAP)...")
                try:
                    check_replies()
                except Exception as check_ex:
                    wlog(f"[SYSTEM] ⚠️ Error en chequeo IMAP: {check_ex}")
                last_imap_check = time.time()
                
            # 5. Si no hay lead, buscar de la cola de ciudades
            if not lead:
                if not search_queue_str.strip():
                    wlog("[SYSTEM] 💤 No hay leads pendientes y la cola de búsqueda está vacía. En espera...")
                    time.sleep(60)
                    continue
                
                # Permitir avanzar en la cola si aún no hemos alcanzado el límite diario de envíos
                if sent_today >= daily_limit:
                    wlog(f"[CLOSER] ⏳ Límite de envíos diario alcanzado. Esperando...")
                    time.sleep(1800)
                    continue
                
                queue = [q.strip() for q in search_queue_str.split('\n') if q.strip()]
                
                # Reinicio/ciclado automático si completamos la cola
                if current_idx >= len(queue):
                    wlog("[SCOUT] 🏁 La cola de ciudades se completó. Reiniciando cola para automatización continua...")
                    with db_lock:
                        db = SessionLocal()
                        set_setting(db, "current_queue_index", "0")
                        db.close()
                    current_idx = 0
                    
                next_query = queue[current_idx]
                wlog(f"[SCOUT] 🔎 Cola automática: Iniciando scraper para '{next_query}'...")
                
                # Guardar fecha de última búsqueda
                with db_lock:
                    db = SessionLocal()
                    set_setting(db, "last_scrape_date", today.strftime("%Y-%m-%d"))
                    db.close()
                
                try:
                    from scraper import run_scraper
                    # El scraper recopila y guarda leads como 'pending'
                    run_scraper(next_query, max_results=daily_limit)
                except Exception as ex:
                    wlog(f"[SCOUT] ⚠️ Error crítico al ejecutar scraper para '{next_query}': {ex}")
                
                # Incrementar índice de cola de búsqueda
                with db_lock:
                    db = SessionLocal()
                    set_setting(db, "current_queue_index", str(current_idx + 1))
                    db.close()
                continue
                
            wlog(f"[CLOSER] 🎯 Procesando prospecto: {lead.email} ({lead.company})")
            
            # 6. Generar contenido dinámico (Spintax / IA) usando la DB o plantilla por defecto
            with db_lock:
                db = SessionLocal()
                email_template = get_setting(db, "email_template_base", CUERPO_HTML_BASE)
                asunto_template = get_setting(db, "email_subject_template", "{Tu sistema de atención al cliente|Automatización con IA para {Empresa}|Una idea de IA para {Empresa}}")
                
                from database import Learning
                recent_learnings = db.query(Learning).order_by(Learning.id.desc()).limit(3).all()
                learnings_list = [l.content for l in recent_learnings]
                db.close()
            
            from ai_engine import process_spintax
            asunto = process_spintax(asunto_template).replace("{Empresa}", lead.company)
            cuerpo_final = generate_ai_variant(email_template, lead.company, lead.name, past_learnings=learnings_list)
            
            # 7. Enviar (send_email maneja su propio bloqueo interno)
            success, err = send_email(lead.id, lead.email, asunto, cuerpo_final)
            
            if success:
                # 8. Pausa anti-spam aleatoria
                with db_lock:
                    db = SessionLocal()
                    delay_min = int(get_setting(db, "delay_min", os.getenv("DELAY_MIN", "120")))
                    delay_max = int(get_setting(db, "delay_max", os.getenv("DELAY_MAX", "300")))
                    db.close()
                
                delay = random.randint(delay_min, delay_max)
                wlog(f"[CLOSER] ✅ Correo enviado con éxito a {lead.email}. Pausa Anti-Spam de {delay} segundos...")
                
                # Dormir en fragmentos cortos para poder interrumpir si se desactiva
                for _ in range(delay):
                    if not is_running: break
                    time.sleep(1)
            else:
                wlog(f"[CLOSER] ❌ Error al enviar a {lead.email}: {err}")
                time.sleep(10)
                
        except Exception as e:
            wlog(f"[SYSTEM] ⚠️ Error en bucle principal del scheduler: {e}")
            time.sleep(30)

def start_bot():
    global is_running, scheduler_thread
    if not is_running:
        is_running = True
        with db_lock:
            db = SessionLocal()
            set_setting(db, "bot_status", "running")
            db.close()
        scheduler_thread = threading.Thread(target=bot_loop, daemon=True)
        scheduler_thread.start()
        return True
    return False

def stop_bot():
    global is_running
    if is_running:
        is_running = False
        with db_lock:
            db = SessionLocal()
            set_setting(db, "bot_status", "stopped")
            db.close()
        return True
    return False
