from fastapi import FastAPI, Depends, BackgroundTasks, WebSocket, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from database import engine, Base, SessionLocal, Lead, SentEmail, Reply, Setting, Learning, get_setting, set_setting, db_lock
from scheduler import start_bot, stop_bot
import scheduler
from scraper import run_scraper, pause_campaign, resume_campaign, stop_campaign
import datetime
import os
import io
import asyncio
from logger import init_logger_loop, connect_ws
import threading
import time
from reply_tracker import check_replies
from pptx_generator import generate_pptx_stream
from ai_engine import _call_gemini

app = FastAPI(title="Egasis Studio API")

def auto_reply_checker():
    """Bucle en segundo plano para revisar respuestas cada 5 minutos"""
    time.sleep(10) # Pequeña pausa inicial
    while True:
        try:
            check_replies()
        except Exception as e:
            pass
        time.sleep(300)

@app.on_event("startup")
def startup_event():
    init_logger_loop(asyncio.get_running_loop())
    t = threading.Thread(target=auto_reply_checker, daemon=True)
    t.start()
    
    # Crear directorios HQ automáticamente en el Escritorio del usuario si no existen (con fallback local)
    desktop_hq = "/Users/jereganza/Desktop/Egasis_HQ"
    try:
        os.makedirs(desktop_hq, exist_ok=True)
    except Exception:
        desktop_hq = os.path.abspath(os.path.join(os.path.dirname(__file__), "Egasis_HQ"))
        os.makedirs(desktop_hq, exist_ok=True)
        
    for folder in ["1_Leads", "2_Reuniones", "3_Presentaciones", "4_Proyectos", "5_Cerebro_Central"]:
        os.makedirs(os.path.join(desktop_hq, folder), exist_ok=True)
        
    # Auto-arranque del agente autónomo
    start_bot()

# Configurar estáticos
os.makedirs("static/css", exist_ok=True)
os.makedirs("static/js", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

# Dependencia DB
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.get("/")
def read_index():
    return FileResponse("static/index.html")

@app.get("/api/metrics")
def get_metrics(db: Session = Depends(get_db)):
    today = datetime.date.today()
    today_start = datetime.datetime(today.year, today.month, today.day)
    
    interested_leads = db.query(Lead).filter(Lead.status.in_(["negociando_horario", "esperando_aprobacion", "confirmado", "agendado"])).count()
    pending_leads = db.query(Lead).filter(Lead.status == "pending").count()
    sent_today = db.query(SentEmail).filter(SentEmail.sent_at >= today_start).count()
    total_contacted = db.query(Lead).count()
    
    bot_status = "running" if scheduler.is_running else "stopped"
    daily_limit = int(get_setting(db, "daily_limit", os.getenv("DAILY_LIMIT", "80")))
    
    return {
        "total_leads": interested_leads,
        "total_contacted": total_contacted,
        "pending_leads": pending_leads,
        "sent_today": sent_today,
        "total_replies": total_contacted,  # mapeado para mostrar Total Contactados en la tarjeta
        "bot_status": bot_status,
        "daily_limit": daily_limit
    }

@app.get("/api/leads")
def get_leads(db: Session = Depends(get_db), limit: int = 50):
    leads = db.query(Lead).order_by(Lead.id.desc()).limit(limit).all()
    return leads

@app.get("/api/replies")
def get_replies(db: Session = Depends(get_db)):
    replies = db.query(Reply).order_by(Reply.id.desc()).limit(20).all()
    out = []
    with db_lock:
        for r in replies:
            d = {c.name: getattr(r, c.name) for c in r.__table__.columns}
            d["lead_status"] = r.lead.status if r.lead else "replied"
            out.append(d)
    return out

# --- NUEVOS ENDPOINTS DE AGENCIA AUTÓNOMA ---

class SettingsRequest(BaseModel):
    search_queue: str
    availability: str
    meeting_link: str

class TemplateRequest(BaseModel):
    subject: str
    body: str

@app.get("/api/settings")
def get_agency_settings(db: Session = Depends(get_db)):
    search_queue = get_setting(db, "search_queue", "Agencias de marketing en Madrid\nAgencias SEO en Barcelona\nDesarrolladores web en Valencia")
    availability = get_setting(db, "availability", "Lunes a las 11:00\nMiércoles a las 16:00")
    meeting_link = get_setting(db, "meeting_link", "https://meet.google.com/xxx-yyyy-zzz")
    current_queue_index = int(get_setting(db, "current_queue_index", "0"))
    return {
        "search_queue": search_queue,
        "availability": availability,
        "meeting_link": meeting_link,
        "current_queue_index": current_queue_index
    }

@app.post("/api/settings")
def save_agency_settings(req: SettingsRequest, db: Session = Depends(get_db)):
    set_setting(db, "search_queue", req.search_queue)
    set_setting(db, "availability", req.availability)
    set_setting(db, "meeting_link", req.meeting_link)
    return {"message": "Configuración guardada correctamente"}

@app.get("/api/settings/template")
def get_template(db: Session = Depends(get_db)):
    subject = get_setting(db, "email_subject_template", "{Reuniones en automático para {Empresa}|Automatizar prospección B2B}")
    from scheduler import CUERPO_HTML_BASE
    body = get_setting(db, "email_template_base", CUERPO_HTML_BASE)
    return {
        "subject": subject,
        "body": body
    }

@app.post("/api/settings/template")
def save_template(req: TemplateRequest, db: Session = Depends(get_db)):
    set_setting(db, "email_subject_template", req.subject)
    set_setting(db, "email_template_base", req.body)
    return {"message": "Plantilla guardada correctamente"}

class LearningRequest(BaseModel):
    content: str

@app.get("/api/learnings")
def get_learnings(db: Session = Depends(get_db)):
    learnings = db.query(Learning).order_by(Learning.created_at.desc()).all()
    return learnings

@app.post("/api/learnings")
def save_learning(req: LearningRequest, db: Session = Depends(get_db)):
    new_learning = Learning(content=req.content)
    db.add(new_learning)
    db.commit()
    return {"message": "Aprendizaje guardado correctamente"}

class StatusUpdateRequest(BaseModel):
    status: str

class ClassificationUpdateRequest(BaseModel):
    classification: str

@app.post("/api/replies/{reply_id}/classification")
def update_reply_classification(reply_id: int, req: ClassificationUpdateRequest, db: Session = Depends(get_db)):
    with db_lock:
        reply = db.query(Reply).filter(Reply.id == reply_id).first()
        if not reply:
            raise HTTPException(status_code=404, detail="Respuesta no encontrada")
        reply.classification = req.classification
        
        # Regenerar propuesta de respuesta basada en la nueva clasificación
        lead = db.query(Lead).filter(Lead.id == reply.lead_id).first()
        if lead:
            from reply_tracker import generate_negotiation_reply, generate_rejection_reply, generate_confirmation_reply, generate_info_requested_reply
            if req.classification == "interested":
                if lead.status == "negociando_horario":
                    subj, body = generate_confirmation_reply(db, lead)
                else:
                    subj, body = generate_negotiation_reply(db, lead)
            elif req.classification == "info_requested":
                subj, body = generate_info_requested_reply(db, lead)
            elif req.classification == "not_interested":
                subj, body = generate_rejection_reply(lead)
            else:
                subj, body = "", ""
                
            reply.proposed_subject = subj
            reply.proposed_reply = body
            
        db.commit()
        return {
            "message": f"Clasificación actualizada a {req.classification}",
            "proposed_subject": reply.proposed_subject,
            "proposed_reply": reply.proposed_reply
        }

@app.post("/api/leads/{lead_id}/status")
def update_lead_status(lead_id: int, req: StatusUpdateRequest, db: Session = Depends(get_db)):
    with db_lock:
        lead = db.query(Lead).filter(Lead.id == lead_id).first()
        if not lead:
            raise HTTPException(status_code=404, detail="Lead no encontrado")
        lead.status = req.status
        db.commit()
    return {"message": f"Estado del lead actualizado a {req.status}"}

@app.delete("/api/leads/{lead_id}")
def delete_lead(lead_id: int, db: Session = Depends(get_db)):
    with db_lock:
        lead = db.query(Lead).filter(Lead.id == lead_id).first()
        if not lead:
            raise HTTPException(status_code=404, detail="Lead no encontrado")
        
        # Eliminar registros dependientes manualmente para evitar errores de clave foránea
        db.query(SentEmail).filter(SentEmail.lead_id == lead_id).delete()
        db.query(Reply).filter(Reply.lead_id == lead_id).delete()
        
        db.delete(lead)
        db.commit()
    return {"success": True, "message": "Lead eliminado correctamente"}

@app.post("/api/leads/{lead_id}/approve-proposed-reply")
def approve_lead_reply(lead_id: int, db: Session = Depends(get_db)):
    with db_lock:
        reply = db.query(Reply).filter(Reply.lead_id == lead_id, Reply.processed_status == "pending_approval").first()
        if not reply:
            raise HTTPException(status_code=404, detail="No hay respuesta pendiente de aprobación para este lead")
            
        lead = db.query(Lead).filter(Lead.id == lead_id).first()
        if not lead:
            raise HTTPException(status_code=404, detail="Lead no encontrado")
            
        try:
            from sender import send_email
            from logger import wlog
            # Enviar el email usando el subject y body propuestos
            send_email(lead_id, reply.from_email, reply.proposed_subject, reply.proposed_reply, new_status=None)
            
            # Actualizar estados dinámicamente según la clasificación
            if reply.classification in ["interested", "info_requested"]:
                if "Confirmada" in (reply.proposed_subject or "") or "confirmada" in (reply.proposed_subject or "") or "meet.google.com" in (reply.proposed_reply or ""):
                    lead.status = "agendado"
                else:
                    lead.status = "negociando_horario"
            elif reply.classification == "not_interested":
                lead.status = "rechazado"
            elif reply.classification == "unsubscribe":
                lead.status = "do_not_contact"
            else:
                lead.status = "replied"
                
            reply.processed_status = "replied"
            db.commit()
            
            wlog(f"✅ Respuesta aprobada y enviada a {reply.from_email} (Permiso otorgado en la tabla de leads)")
            return {"success": True, "message": "Respuesta enviada correctamente"}
        except Exception as e:
            from logger import wlog
            wlog(f"❌ Error al enviar respuesta aprobada desde leads: {e}")
            raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/meetings/{lead_id}/brief")
def get_call_brief(lead_id: int, db: Session = Depends(get_db)):
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead no encontrado")
        
    prompt = f"""
    Eres un asesor de ventas B2B experto en automatización y soluciones de IA de Egasis Studio.
    Tengo una reunión de ventas con la empresa: "{lead.company}".
    Esta empresa fue encontrada a través de la búsqueda de Google Maps: "{lead.source or 'Búsqueda general'}".
    Su correo de contacto es: {lead.email}

    Redacta un "Call Brief" de ventas sumamente estratégico e hiper-personalizado en formato HTML estructurado (usa etiquetas <p>, <ul>, <li>, <h3>, <strong>).
    Analiza dinámicamente el nombre y el contexto del lead para deducir su sector y modelo de negocio.
    Debe contener la siguiente estructura exacta:
    
    <h3>1. Contexto Comercial de {lead.company}</h3>
    <p>Describe de forma analítica su probable modelo de negocio, su público objetivo y cómo consiguen clientes hoy.</p>
    
    <h3>2. Puntos Fuertes (Pros)</h3>
    <ul>
      <li>Presencia digital, visibilidad en Maps y canales de contacto activos.</li>
      <li>Fortalezas operativas deducidas del sector.</li>
    </ul>
    
    <h3>3. Dolores Críticos que la IA resolverá</h3>
    <p>Detalla 3 o 4 problemas graves comunes en su operación diaria (por ejemplo: lentitud al responder a consultas fuera de hora, personal saturado agendando citas, pérdida de leads cálidos por falta de seguimiento comercial estructurado).</p>
    
    <h3>4. Ángulo de Venta Recomendado (Egasis Studio)</h3>
    <p>Propón la estrategia de pitch comercial para presentar la demo de Egasis Studio. Recomienda vender una solución de IA específica para ellos (por ejemplo: Recepcionista Médica IA 24/7 en WhatsApp, Clon de Closer de Ventas B2B, o automatización de propuestas comerciales) detallando el retorno de inversión (ROI) estimado y el impacto operativo.</p>
    
    Mantenlo sumamente práctico, persuasivo y comercial. Ve directo al valor financiero y operativo del sistema.
    """
    brief_content = _call_gemini(prompt)
    if not brief_content or "Error" in brief_content:
        brief_content = f"<h3>Análisis de Venta</h3><p>Prepara la propuesta enfocándote en la automatización de WhatsApp y agenda de turnos en piloto automático para {lead.company}.</p>"
    else:
        # Limpiar bloques de código markdown si Gemini los agregó
        brief_content = brief_content.strip()
        if brief_content.startswith("```html"):
            brief_content = brief_content[7:]
        elif brief_content.startswith("```"):
            brief_content = brief_content[3:]
        if brief_content.endswith("```"):
            brief_content = brief_content[:-3]
        brief_content = brief_content.strip()
    
    return {"company": lead.company, "brief": brief_content}

@app.get("/api/meetings/{lead_id}/download-pptx")
def download_pitch_pptx(lead_id: int, db: Session = Depends(get_db)):
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead no encontrado")
    
    # Generar en buffer de memoria
    stream = io.BytesIO()
    generate_pptx_stream(lead.company, stream)
    stream.seek(0)
    
    filename = f"Pitch_{lead.company.replace(' ', '_')}.pptx"
    return StreamingResponse(
        stream,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

@app.get("/api/meetings/{lead_id}/download-demo")
def download_demo_zip(lead_id: int, db: Session = Depends(get_db)):
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead no encontrado")
    
    import zipfile
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        # README.md
        readme_content = f"""# Prototipo de Asistente WhatsApp - {lead.company}

Este archivo comprimido contiene la simulación interactiva a doble pantalla diseñada a medida para presentar al cliente.

## ¿Cómo usar la Demo Visual?
1. Descomprime este archivo ZIP.
2. Haz doble clic en el archivo `index.html` para abrirlo en cualquier navegador (Chrome, Safari, Edge, etc.), tanto en tu computadora como en tu celular.
3. ¡Podrás chatear en vivo con la IA a la izquierda y ver cómo se actualiza la terminal de control y la planilla Excel en tiempo real a la derecha!
"""
        zip_file.writestr("README.md", readme_content)
        
        # index.html
        html_template = r"""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Demo Turnos Clínicos IA | Split Screen</title>
    <link href="https://fonts.googleapis.com/css2?family=Roboto:wght@400;500;700&family=Fira+Code:wght@400;500&display=swap" rel="stylesheet">
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: 'Roboto', sans-serif;
            background-color: #f0f2f5;
            color: #111;
            height: 100vh;
            overflow: hidden;
        }

        /* MODAL DE BIENVENIDA */
        .modal-overlay {
            position: fixed; top: 0; left: 0; width: 100vw; height: 100vh;
            background: rgba(0, 0, 0, 0.6); backdrop-filter: blur(5px);
            display: flex; justify-content: center; align-items: center;
            z-index: 1000;
        }
        .modal-content {
            background: white; padding: 30px; border-radius: 12px;
            max-width: 500px; box-shadow: 0 20px 40px rgba(0,0,0,0.3);
        }
        .modal-content h2 { color: #008069; margin-bottom: 15px; }
        .modal-content p { margin-bottom: 10px; color: #444; font-size: 15px; line-height: 1.5; }
        .modal-content ul { margin-left: 20px; margin-bottom: 20px; color: #444; font-size: 14px; }
        .modal-content li { margin-bottom: 8px; }
        .start-btn {
            background-color: #00a884; color: white; border: none;
            padding: 12px 24px; border-radius: 8px; font-size: 16px;
            font-weight: bold; cursor: pointer; width: 100%; transition: 0.2s;
        }
        .start-btn:hover { background-color: #008069; }
        .hidden { display: none !important; }

        .dashboard-layout {
            display: flex;
            height: 100vh;
            width: 100vw;
        }

        /* PANEL IZQUIERDO - CELULAR */
        .left-panel {
            flex: 1;
            display: flex;
            justify-content: center;
            align-items: center;
            background-color: #e5e5f7;
            background-image: radial-gradient(#00a884 0.5px, #e5e5f7 0.5px);
            background-size: 10px 10px;
            border-right: 2px solid #ddd;
        }

        .phone-mockup {
            width: 350px;
            height: 680px;
            background-color: #efeae2;
            border-radius: 40px;
            box-shadow: 0 25px 50px rgba(0,0,0,0.3), inset 0 0 0 10px #111;
            display: flex;
            flex-direction: column;
            overflow: hidden;
            position: relative;
        }

        .phone-notch {
            position: absolute;
            top: 10px;
            left: 50%;
            transform: translateX(-50%);
            width: 120px;
            height: 25px;
            background-color: #111;
            border-bottom-left-radius: 15px;
            border-bottom-right-radius: 15px;
            z-index: 10;
        }

        .wa-header {
            background-color: #008069;
            color: white;
            padding: 35px 15px 15px;
            display: flex;
            align-items: center;
            gap: 12px;
        }

        .wa-avatar {
            width: 40px;
            height: 40px;
            background-color: #ccc;
            border-radius: 50%;
            display: flex;
            justify-content: center;
            align-items: center;
            font-weight: bold;
            color: #333;
            font-size: 14px;
        }

        .wa-info h2 { font-size: 16px; font-weight: 500; }
        .wa-info p { font-size: 12px; opacity: 0.8; }

        .wa-chat-bg {
            flex: 1;
            background-image: url('https://user-images.githubusercontent.com/15075759/28719144-86dc0f70-73b1-11e7-911d-60d70fcded21.png');
            background-size: cover;
            padding: 15px;
            overflow-y: auto;
            display: flex;
            flex-direction: column;
        }

        .chat-messages {
            display: flex;
            flex-direction: column;
            gap: 8px;
        }

        .message {
            padding: 8px 12px;
            border-radius: 8px;
            max-width: 85%;
            font-size: 14.5px;
            line-height: 1.4;
            position: relative;
            box-shadow: 0 1px 2px rgba(0,0,0,0.1);
            word-wrap: break-word;
        }

        .bot-message {
            background-color: #ffffff;
            align-self: flex-start;
            border-top-left-radius: 0;
        }

        .user-message {
            background-color: #d9fdd3;
            align-self: flex-end;
            border-top-right-radius: 0;
        }

        .wa-input-area {
            background-color: #f0f2f5;
            padding: 10px;
            display: flex;
            gap: 8px;
            align-items: center;
        }

        .wa-input-area input {
            flex: 1;
            padding: 12px;
            border-radius: 20px;
            border: none;
            outline: none;
            font-size: 15px;
        }

        .wa-send-btn {
            background-color: #00a884;
            color: white;
            border: none;
            width: 40px;
            height: 40px;
            border-radius: 50%;
            cursor: pointer;
            font-size: 18px;
            display: flex;
            justify-content: center;
            align-items: center;
        }

        .wa-icon { background: none; border: none; font-size: 24px; color: #8696a0; }

        /* PANEL DERECHO - DASHBOARD */
        .right-panel {
            flex: 1.5;
            padding: 40px;
            display: flex;
            flex-direction: column;
            gap: 30px;
            overflow-y: auto;
        }

        .panel-header h1 { font-size: 28px; margin-bottom: 8px; color: #1f2937; }
        .panel-header p { color: #6b7280; font-size: 16px; }

        .matrix-terminal {
            background-color: #1e1e1e;
            border-radius: 12px;
            box-shadow: 0 10px 25px rgba(0,0,0,0.2);
            overflow: hidden;
            height: 250px;
            display: flex;
            flex-direction: column;
        }

        .terminal-header {
            background-color: #323233;
            padding: 10px 15px;
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .dot { width: 12px; height: 12px; border-radius: 50%; }
        .red { background-color: #ff5f56; }
        .yellow { background-color: #ffbd2e; }
        .green { background-color: #27c93f; }
        .title { color: #ccc; font-family: 'Fira Code', monospace; font-size: 13px; margin-left: 10px; }

        .terminal-body {
            padding: 15px;
            flex: 1;
            font-family: 'Fira Code', monospace;
            color: #4ade80;
            font-size: 13px;
            overflow-y: auto;
            display: flex;
            flex-direction: column;
            gap: 5px;
        }

        .excel-view {
            background-color: white;
            border-radius: 12px;
            box-shadow: 0 10px 25px rgba(0,0,0,0.1);
            overflow: hidden;
            border: 1px solid #e5e7eb;
        }

        .excel-header {
            background-color: #107c41;
            color: white;
            padding: 15px;
            font-weight: 600;
            font-size: 16px;
        }

        .excel-table {
            width: 100%;
            border-collapse: collapse;
        }

        .excel-table th {
            background-color: #f3f4f6;
            text-align: left;
            padding: 12px 15px;
            border-bottom: 2px solid #e5e7eb;
            color: #374151;
        }

        .excel-table td {
            padding: 12px 15px;
            border-bottom: 1px solid #e5e7eb;
            color: #111827;
        }

        .badge {
            background-color: #d1fae5;
            color: #065f46;
            padding: 4px 8px;
            border-radius: 12px;
            font-size: 12px;
            font-weight: bold;
        }

        @media (max-width: 900px) {
            .dashboard-layout {
                flex-direction: column;
                height: auto;
                overflow-y: auto;
            }
            body {
                overflow-y: auto;
            }
            .left-panel {
                padding: 40px 20px;
                border-right: none;
                border-bottom: 2px solid #ddd;
            }
            .phone-mockup {
                width: 100%;
                max-width: 400px;
                height: 80vh;
                border-radius: 30px;
            }
            .right-panel {
                padding: 20px;
                overflow-y: visible;
            }
        }
    </style>
</head>
<body>
    <!-- MODAL DE BIENVENIDA -->
    <div id="welcomeModal" class="modal-overlay">
        <div class="modal-content">
            <h2>👋 ¡Bienvenido a la Demo de __CLINIC_NAME__!</h2>
            <p>Este es un Simulador de Inteligencia Artificial para la clínica.</p>
            <p><strong>Para probarlo, podés:</strong></p>
            <ul id="modal-bullets">
                <!-- Se poblará dinámicamente según si es dental o estética -->
            </ul>
            <p style="background-color: #f0fdf4; padding: 10px; border-left: 4px solid #16a34a; border-radius: 4px; font-size: 13px;">💡 <strong>Aclaración:</strong> Esto es solo una Demo offline. Todo el sistema de Egasis Studio es 100% personalizable y se conecta a tus sistemas de gestión (Calendar, CRMs, etc).</p>
            <p><em>Al finalizar el chat, la tabla de "Agenda de Turnos" se actualizará mágicamente sola en vivo.</em></p>
            <button id="startDemoBtn" class="start-btn">¡Entendido, arrancar demo!</button>
        </div>
    </div>

    <div class="dashboard-layout">
        
        <!-- PANEL IZQUIERDO: CELULAR (WhatsApp) -->
        <div class="left-panel">
            <div class="phone-mockup">
                <div class="phone-notch"></div>
                <div class="wa-header">
                    <div class="wa-avatar" style="background-color: #dcf8c6; color: #075e54;">🦷</div>
                    <div class="wa-info">
                        <h2>Martina (AI Assistant)</h2>
                        <p>__CLINIC_NAME__</p>
                    </div>
                </div>
                
                <div class="wa-chat-bg">
                    <div class="chat-messages" id="chatMessages">
                        <div class="message bot-message" id="welcome-chat-msg">
                            ¡Hola! Somos la clínica __CLINIC_NAME__ ✨. ¿En qué podemos ayudarte hoy?
                        </div>
                    </div>
                </div>

                <form class="wa-input-area" id="chatForm" onsubmit="event.preventDefault(); return false;">
                    <button type="button" class="wa-icon">😊</button>
                    <input type="text" id="userInput" placeholder="Mensaje" autocomplete="off" required>
                    <button type="submit" id="sendBtn" class="wa-send-btn">➤</button>
                </form>
            </div>
        </div>

        <!-- PANEL DERECHO: DASHBOARD -->
        <div class="right-panel">
            <div class="panel-header">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <h1>Recepcionista Virtual Autónoma</h1>
                    <button id="resetDemoBtn" style="background-color: #ef4444; color: white; border: none; padding: 6px 12px; border-radius: 6px; cursor: pointer; font-size: 13px; font-weight: bold;">Limpiar Demo</button>
                </div>
                <p>A la izquierda: la experiencia de tus pacientes en WhatsApp. A la derecha: cómo la IA agenda los turnos automáticamente en tu calendario.</p>
            </div>
            
            <div class="matrix-terminal">
                <div class="terminal-header">
                    <span class="dot red"></span><span class="dot yellow"></span><span class="dot green"></span>
                    <span class="title">terminal - Receptionist Brain</span>
                </div>
                <div class="terminal-body" id="terminalLogs">
                    <p style="color: #60a5fa;">> Sistema conectado a WhatsApp Business de __CLINIC_NAME__.</p>
                    <p style="color: #60a5fa;">> Memoria cargada. Esperando consultas médicas...</p>
                </div>
            </div>

            <div class="excel-view">
                <div class="excel-header" style="background-color: #107c41;">
                    <span class="excel-icon">📅</span> agenda_turnos.csv (Sincronización en vivo)
                </div>
                <table class="excel-table">
                    <thead>
                        <tr>
                            <th>Paciente</th>
                            <th>DNI</th>
                            <th>Tratamiento</th>
                            <th>Horario Asignado</th>
                        </tr>
                    </thead>
                    <tbody id="leadsTableBody">
                        <tr><td colspan="4" style="text-align: center; color: #888;">Agenda libre. Esperando nuevos turnos...</td></tr>
                    </tbody>
                </table>
            </div>
        </div>
    </div>

    <script>
        const chatForm = document.getElementById('chatForm');
        const userInput = document.getElementById('userInput');
        const chatMessages = document.getElementById('chatMessages');
        const terminalLogs = document.getElementById('terminalLogs');
        const leadsTableBody = document.getElementById('leadsTableBody');
        const welcomeModal = document.getElementById('welcomeModal');
        const startDemoBtn = document.getElementById('startDemoBtn');
        const resetDemoBtn = document.getElementById('resetDemoBtn');
        
        // Auto-detección de tipo de clínica
        const clinicName = "__CLINIC_NAME__";
        const isDental = clinicName.toLowerCase().includes("dental") || clinicName.toLowerCase().includes("odont") || clinicName.toLowerCase().includes("dent") || clinicName.toLowerCase().includes("sonris");
        
        const treatments = isDental 
            ? ["Carillas de Porcelana", "Blanqueamiento Dental", "Implantes Dentales"]
            : ["Botox Facial", "Ácido Hialurónico", "Depilación Láser Soprano"];

        // Rellenar modal con viñetas personalizadas
        const modalBullets = document.getElementById("modal-bullets");
        modalBullets.innerHTML = `
            <li>Preguntar precios de <b>${treatments[0]}</b>, <b>${treatments[1]}</b> o <b>${treatments[2]}</b>.</li>
            <li>Pedir un turno (el bot te dará opciones de horarios disponibles).</li>
            <li>Dar tus datos (Nombre y DNI) para confirmar el turno.</li>
        `;

        // Personalizar mensaje de bienvenida del chat
        const welcomeChatMsg = document.getElementById("welcome-chat-msg");
        welcomeChatMsg.innerHTML = `¡Hola! Somos la clínica <strong>${clinicName}</strong> ✨. ¿En qué podemos ayudarte hoy? ¿Te interesa conocer nuestros tratamientos o prefieres agendar una consulta de valoración gratuita?`;

        if (startDemoBtn) {
            startDemoBtn.addEventListener('click', () => {
                welcomeModal.classList.add('hidden');
                userInput.focus();
            });
        }

        function addLog(message, color = "#4ade80") {
            const p = document.createElement('p');
            p.style.color = color;
            p.textContent = `> ${new Date().toLocaleTimeString()} - ${message}`;
            terminalLogs.appendChild(p);
            terminalLogs.scrollTop = terminalLogs.scrollHeight;
        }

        let agenda = [];
        let stage = 0;
        let selectedTreatment = "";
        let selectedTime = "";
        let patientName = "";
        let patientDNI = "";

        function renderTable() {
            if (agenda.length > 0) {
                leadsTableBody.innerHTML = '';
                agenda.forEach(order => {
                    const tr = document.createElement('tr');
                    tr.innerHTML = `
                        <td><b>${order.Paciente || '-'}</b></td>
                        <td>${order.DNI || '-'}</td>
                        <td>${order.Tratamiento || '-'}</td>
                        <td><span class="badge">${order.Horario || '-'}</span></td>
                    `;
                    leadsTableBody.appendChild(tr);
                });
            } else {
                leadsTableBody.innerHTML = '<tr><td colspan="4" style="text-align: center; color: #888;">Agenda libre. Esperando nuevos turnos...</td></tr>';
            }
        }

        if (resetDemoBtn) {
            resetDemoBtn.addEventListener('click', () => {
                if(confirm("¿Seguro que quieres borrar la agenda y vaciar el chat para empezar una demo de cero?")) {
                    agenda = [];
                    renderTable();
                    
                    chatMessages.innerHTML = `<div class="message bot-message">¡Hola! Somos la clínica <strong>${clinicName}</strong> ✨. ¿En qué podemos ayudarte hoy?</div>`;
                    terminalLogs.innerHTML = `<p style="color: #60a5fa;">> Sistema conectado a WhatsApp Business de ${clinicName}.</p><p>> Memoria cargada. Esperando consultas médicas...</p>`;
                    
                    stage = 0;
                    selectedTreatment = "";
                    selectedTime = "";
                    patientName = "";
                    patientDNI = "";
                    
                    addLog('[SYSTEM] Demo reiniciada. Agenda vaciada. Nueva memoria de conversación activada.', '#ffbd2e');
                }
            });
        }

        chatForm.addEventListener('submit', (e) => {
            e.preventDefault();
            const message = userInput.value.trim();
            if (!message) return;

            appendMessage(message, 'user');
            userInput.value = '';
            
            addLog(`[USER INPUT] Analizando intención del paciente: "${message}"`, '#fef08a');
            
            const typingId = showTypingIndicator();

            setTimeout(() => {
                removeMessage(typingId);
                const reply = getAIResponse(message);
                appendMessage(reply, 'bot');
                addLog('[AI RECEPTIONIST] Respuesta enviada con éxito.', '#60a5fa');
                renderTable();
            }, 1200);
        });

        function appendMessage(text, sender) {
            const msgDiv = document.createElement('div');
            msgDiv.classList.add('message');
            msgDiv.classList.add(sender === 'user' ? 'user-message' : 'bot-message');
            msgDiv.innerHTML = text.replace(/\n/g, '<br>');
            chatMessages.appendChild(msgDiv);
            chatMessages.parentElement.scrollTop = chatMessages.parentElement.scrollHeight;
        }

        function showTypingIndicator() {
            const id = 'typing-' + Date.now();
            const msgDiv = document.createElement('div');
            msgDiv.id = id;
            msgDiv.classList.add('message', 'bot-message');
            msgDiv.textContent = 'escribiendo...';
            chatMessages.appendChild(msgDiv);
            chatMessages.parentElement.scrollTop = chatMessages.parentElement.scrollHeight;
            return id;
        }

        function removeMessage(id) {
            const el = document.getElementById(id);
            if (el) el.remove();
        }

        function getAIResponse(userInputText) {
            const input = userInputText.toLowerCase();
            
            // Detección de precios y costos
            if (input.includes("precio") || input.includes("cuanto") || input.includes("costo") || input.includes("sale") || input.includes("cobran") || input.includes("valor")) {
                addLog('[DECISION] Detectada consulta de precios. Derivando a Valoración Gratuita.', '#ffbd2e');
                return `Nuestros tratamientos en <strong>${clinicName}</strong> (como ${treatments[0]} o ${treatments[1]}) se cotizan de forma 100% personalizada. La consulta de diagnóstico y valoración es totalmente <strong>gratuita y sin compromiso</strong>. ¿Te gustaría agendar una cita para que te evalúe el doctor?`;
            }
            
            // Detección de tratamientos
            if (input.includes("tratamiento") || input.includes("servicio") || input.includes("hacen") || input.includes("botox") || input.includes("laser") || input.includes("carilla") || input.includes("diente") || input.includes("hialuronico") || input.includes("blanquea") || input.includes("implante")) {
                addLog('[DECISION] Paciente solicita información de tratamientos.', '#27c93f');
                return `En <strong>${clinicName}</strong> somos especialistas en estética avanzada. Ofrecemos principalmente:<br><br>• <strong>${treatments[0]}</strong><br>• <strong>${treatments[1]}</strong><br>• <strong>${treatments[2]}</strong><br><br>¿Te gustaría agendar una consulta de valoración gratuita sobre alguno de ellos?`;
            }

            // Iniciar flujo de agendamiento
            if (input.includes("turno") || input.includes("agendar") || input.includes("cita") || input.includes("reservar") || input.includes("consulta")) {
                stage = 1;
                addLog('[WORKFLOW] Iniciando proceso de agendamiento de turnos.', '#60a5fa');
                return `¡Excelente! Te agendamos la cita de valoración gratuita. ¿Qué tratamiento te interesa realizarte? (Por ejemplo: <strong>${treatments[0]}</strong>, <strong>${treatments[1]}</strong> o <strong>${treatments[2]}</strong>)`;
            }

            // Procesar etapas de agendamiento
            if (stage === 1) {
                // Guarda tratamiento
                selectedTreatment = userInputText;
                stage = 2;
                addLog(`[WORKFLOW] Tratamiento seleccionado: "${selectedTreatment}". Consultando disponibilidad...`, '#27c93f');
                return `Perfecto, agendamos para <strong>${selectedTreatment}</strong>. Contamos con turnos disponibles esta semana. ¿Prefieres <strong>miércoles por la mañana (11:30 AM)</strong> o <strong>viernes por la tarde (4:00 PM)</strong>?`;
            }

            if (stage === 2) {
                // Guarda horario
                selectedTime = userInputText.includes("mierco") || userInputText.includes("miérco") || userInputText.includes("mañana") ? "Miércoles 11:30 AM" : "Viernes 4:00 PM";
                stage = 3;
                addLog(`[WORKFLOW] Horario seleccionado: "${selectedTime}". Solicitando datos personales del paciente.`, '#60a5fa');
                return `Excelente opción. Para reservar el horario del <strong>${selectedTime}</strong>, por favor indícame tu nombre completo (Nombre y Apellido).`;
            }

            if (stage === 3) {
                // Guarda nombre
                patientName = userInputText;
                stage = 4;
                addLog(`[WORKFLOW] Nombre registrado: "${patientName}". Solicitando DNI para finalizar.`, '#a78bfa');
                return `Muchas gracias, <strong>${patientName}</strong>. Por último, indícame tu número de DNI o documento para formalizar la cita en nuestro sistema.`;
            }

            if (stage === 4) {
                // Guarda DNI y confirma
                patientDNI = userInputText;
                stage = 0;
                
                // Agregar turno a la agenda simulada
                const nuevoTurno = {
                    Paciente: patientName,
                    DNI: patientDNI,
                    Tratamiento: selectedTreatment,
                    Horario: selectedTime
                };
                agenda.push(nuevoTurno);
                
                addLog(`[DATABASE] Insertando turno en agenda_turnos.csv para ${patientName}...`, '#4ade80');
                addLog('[SYSTEM] Turno sincronizado correctamente. Notificación de confirmación enviada a WhatsApp.', '#4ade80');
                
                return `¡Todo listo! Tu turno de valoración gratuita para <strong>${selectedTreatment}</strong> ha sido agendado con éxito el <strong>${selectedTime}</strong>.<br><br>Te hemos enviado un recordatorio. ¡Te esperamos en <strong>${clinicName}</strong>!`;
            }

            // Respuestas estándar
            if (input.includes("hola") || input.includes("buenas") || input.includes("buenos") || input.includes("que tal") || input.includes("alguien")) {
                return `¡Hola! Qué gusto saludarte. ¿Te gustaría conocer nuestros tratamientos en <strong>${clinicName}</strong>, consultar precios o agendar una consulta de valoración gratuita directamente?`;
            }

            if (input.includes("gracias") || input.includes("adios") || input.includes("chau") || input.includes("perfecto") || input.includes("listo")) {
                return `¡De nada! En <strong>${clinicName}</strong> estamos a tu entera disposición. Si necesitas agendar un turno más adelante, solo escríbenos por aquí. ¡Que tengas un excelente día! 😊`;
            }

            return `Entendido. Soy el asistente virtual inteligente de <strong>${clinicName}</strong>. ¿Te gustaría que agendemos una cita de valoración gratuita para resolver tus dudas directamente en la clínica?`;
        }
    </script>
</body>
</html>"""
        
        # Guardar en el ZIP
        html_content = html_template.replace("__CLINIC_NAME__", lead.company)
        zip_file.writestr("index.html", html_content)
        
        # Escribir código Python en el ZIP como extra
        agent_content = f"""# Agente de atención para {lead.company}
import os

class ClinicaAgent:
    def __init__(self):
        self.clinic_name = "{lead.company}"
        print(f"[*] Inicializando agente para {{self.clinic_name}}...")
        
    def responder(self, mensaje):
        if "precio" in mensaje.lower():
            return "Nuestros tratamientos son personalizados. ¿Te gustaría agendar una cita de valoración gratuita?"
        return "Hola, gracias por comunicarte. ¿En qué podemos ayudarte hoy?"
"""
        zip_file.writestr("agente_atencion.py", agent_content)
        
        test_content = """# Script de pruebas interactivo
from agente_atencion import ClinicaAgent

def main():
    agent = ClinicaAgent()
    print("=== Consola de Pruebas de IA ===")
    while True:
        msg = input("Cliente: ")
        if msg.lower() == 'salir':
            break
        print("IA:", agent.responder(msg))

if __name__ == "__main__":
    main()
"""
        zip_file.writestr("test_agent.py", test_content)
        
    stream.seek(0)
    filename = f"Demo_{lead.company.replace(' ', '_')}.zip"
    return StreamingResponse(
        stream,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

# --- FIN NUEVOS ENDPOINTS ---

class ScraperRequest(BaseModel):
    query: str
    max_results: int = 50

@app.post("/api/scraper/start")
def start_scraper(req: ScraperRequest, background_tasks: BackgroundTasks):
    background_tasks.add_task(run_scraper, req.query, req.max_results)
    return {"message": f"Scraper iniciado para: {req.query}"}

@app.post("/api/bot/start")
def start_bot_endpoint():
    res = start_bot()
    return {"message": "Bot iniciado", "success": res}

@app.post("/api/bot/stop")
def stop_bot_endpoint():
    res = stop_bot()
    return {"message": "Bot detenido", "success": res}

@app.websocket("/ws/logs")
async def websocket_logs(websocket: WebSocket):
    await connect_ws(websocket)

@app.post("/api/scraper/pause")
def api_scraper_pause():
    pause_campaign()
    return {"message": "Campaña pausada"}

@app.post("/api/scraper/resume")
def api_scraper_resume():
    resume_campaign()
    return {"message": "Campaña reanudada"}

@app.post("/api/scraper/stop")
def api_scraper_stop():
    stop_campaign()
    return {"message": "Detención solicitada"}

@app.post("/api/inbox/sync")
def api_inbox_sync(background_tasks: BackgroundTasks):
    background_tasks.add_task(check_replies)
    return {"message": "Sincronización iniciada en segundo plano."}

class ApproveReplyRequest(BaseModel):
    subject: str
    body: str

@app.post("/api/replies/{reply_id}/approve")
def approve_reply(reply_id: int, req: ApproveReplyRequest, db: Session = Depends(get_db)):
    reply = db.query(Reply).filter(Reply.id == reply_id).first()
    if not reply:
        raise HTTPException(status_code=404, detail="Respuesta no encontrada")
        
    lead = db.query(Lead).filter(Lead.id == reply.lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead no encontrado")
        
    try:
        from sender import send_email
        from logger import wlog
        # Enviar el email usando el subject y body aprobados por el usuario
        send_email(lead.id, reply.from_email, req.subject, req.body, new_status=None)
        
        # Actualizar estado del lead según el tipo de clasificación
        if reply.classification == "interested":
            # Si el correo contiene palabras de confirmación o sala de Meet
            if "Confirmada" in req.subject or "confirmada" in req.subject or "meet.google.com" in req.body:
                lead.status = "agendado"
            else:
                lead.status = "negociando_horario"
        elif reply.classification == "not_interested":
            lead.status = "rechazado"
        else:
            lead.status = "replied"
            
        reply.processed_status = "replied"
        reply.proposed_reply = req.body
        reply.proposed_subject = req.subject
        db.commit()
        
        wlog(f"✅ Respuesta aprobada y enviada a {reply.from_email}!")
        return {"success": True, "message": "Respuesta enviada correctamente"}
    except Exception as e:
        from logger import wlog
        wlog(f"❌ Error al enviar respuesta aprobada: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/replies/{reply_id}/dismiss")
def dismiss_reply(reply_id: int, db: Session = Depends(get_db)):
    reply = db.query(Reply).filter(Reply.id == reply_id).first()
    if not reply:
        raise HTTPException(status_code=404, detail="Respuesta no encontrada")
        
    lead = db.query(Lead).filter(Lead.id == reply.lead_id).first()
    if lead:
        lead.status = "replied"
        
    reply.processed_status = "read"
    db.commit()
    
    from logger import wlog
    wlog(f"🗑️ Respuesta de {reply.from_email} descartada por el usuario.")
    return {"success": True, "message": "Respuesta descartada"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
