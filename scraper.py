import urllib.parse
import time
import re
import requests
import random
import datetime
from bs4 import BeautifulSoup
from database import SessionLocal, Lead, SentEmail, get_setting, ProcessedBusiness, db_lock
from sender import send_email
from ai_engine import generate_ai_variant, process_spintax
from logger import wlog
import os

campaign_state = {
    "is_running": False,
    "is_paused": False,
    "should_stop": False
}

def pause_campaign():
    campaign_state["is_paused"] = True
    wlog("\n⏸️ CAMPAÑA PAUSADA. El bot está congelado esperando orden...")

def resume_campaign():
    campaign_state["is_paused"] = False
    wlog("\n▶️ CAMPAÑA REANUDADA. Continuando operaciones...")

def stop_campaign():
    campaign_state["should_stop"] = True
    wlog("\n🛑 DETENCIÓN SOLICITADA. Cancelando campaña de forma segura...")

CUERPO_HTML_BASE = """\
<html>
  <body>
    <p>{Hola|Estimado|Qué tal} <b>{Nombre}</b>,</p>
    <p>Estuve viendo el perfil de <b>{Empresa}</b> y me encanta cómo trabajan.</p>
    <p>Somos Egasis Studio y ayudamos a agencias B2B a escalar mediante un <b>Sistema de Prospección Autónomo</b>. Construimos un software que busca clientes ideales, analiza sus páginas web, extrae correos y les envía propuestas personalizadas mediante IA, 100% en piloto automático.</p>
    <p>Actúa como un representante de ventas que trabaja 24/7, agendando reuniones calificadas directamente en tu calendario sin que tengas que mover un dedo.</p>
    <p>¿Tendrían 10 minutos la próxima semana para que les muestre cómo les generaría reuniones a ustedes?</p>
    <br>
    <p>Un saludo,<br>Jeremías</p>
  </body>
</html>
"""

def extraer_emails(texto):
    email_regex = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
    encontrados = set(email_regex.findall(texto))
    mailtos = re.findall(r'mailto:([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', texto)
    encontrados.update(mailtos)
    
    limpios = []
    # Avoid false positives like image files, sentry logs, generic emails
    excluded_keywords = ['example', 'wix', 'sentry', 'png', 'jpg', 'jpeg', 'gif', 'svg', 'webp', 'google', 'bootstrap', 'jquery']
    for e in encontrados:
        e_low = e.lower()
        if not any(x in e_low for x in excluded_keywords):
            limpios.append(e_low)
    return limpios

def run_scraper(queries_input: str, max_results: int = 50):
    """Scrapea leads de Google Maps y los guarda en la base de datos como 'pending'."""
    global campaign_state
    campaign_state["is_running"] = True
    campaign_state["is_paused"] = False
    campaign_state["should_stop"] = False
    
    from playwright.sync_api import sync_playwright
    db = SessionLocal()
    
    queries = [q.strip() for q in queries_input.split(',') if q.strip()]
    
    wlog(f"[SCOUT] 🚀 Iniciando campaña de prospección: {len(queries)} búsquedas programadas.")
    today_date = datetime.date.today()
    leads_scraped_current_run = 0
    
    with sync_playwright() as p:
        wlog("[SCOUT] 🤖 Abriendo navegador autónomo seguro...")
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36")
        page = context.new_page()
        
        for q_index, current_query in enumerate(queries, 1):
            if campaign_state["should_stop"]: break
            while campaign_state["is_paused"]: time.sleep(1)
            
            wlog(f"[SCOUT] 🔍 [{q_index}/{len(queries)}] Buscando en Google Maps: '{current_query}'")
            
            search_url = f"https://www.google.com/maps/search/{urllib.parse.quote(current_query)}"
            page.goto(search_url)
            
            try:
                page.click("button:has-text('Aceptar todo')", timeout=3000)
            except: pass
            
            wlog(f"[SCOUT] ⏳ Cargando resultados de '{current_query}' (haciendo scroll)...")
            try:
                page.wait_for_selector('a[href*="/maps/place/"]', timeout=10000)
            except:
                wlog(f"[SCOUT] ⚠️ No se encontraron resultados para '{current_query}'. Saltando...")
                continue
                
            for i in range(8):
                page.mouse.wheel(0, 4000)
                time.sleep(1)
                
            lugares = page.query_selector_all('a[href*="/maps/place/"]')
            wlog(f"[SCOUT] ✅ Encontrados {len(lugares)} negocios para analizar en '{current_query}'.")
            
            for i, lugar in enumerate(lugares):
                if campaign_state["should_stop"]: break
                while campaign_state["is_paused"]: time.sleep(1)
                
                if leads_scraped_current_run >= max_results:
                    wlog(f"[SCOUT] 🛑 Límite de leads para esta campaña alcanzado ({max_results}). Deteniendo.")
                    break
                    
                try:
                    nombre = "Empresa"
                    aria_label = lugar.get_attribute('aria-label')
                    if aria_label:
                        nombre = aria_label.strip()
                        
                    # Comprobación de caché de procesados para no hacer clicks o scrapes redundantes
                    if nombre != "Empresa":
                        with db_lock:
                            existe_procesado = db.query(ProcessedBusiness).filter(ProcessedBusiness.company_name == nombre).first()
                        if existe_procesado:
                            print(f"[SCOUT] [DEBUG] Saltando {nombre} (ya analizado anteriormente)")
                            continue
                    
                    lugar.click(force=True)
                    page.wait_for_timeout(2000)
                    
                    if nombre == "Empresa":
                        nombre_h1 = page.query_selector('h1').inner_text()
                        if nombre_h1 and nombre_h1.strip().lower() != "resultados":
                            nombre = nombre_h1.strip()
                    
                    print(f"[SCOUT] [DEBUG] Analizando sitio web de: {nombre}")
                    
                    website = None
                    try:
                        web_el = page.query_selector('a[data-item-id="authority"]')
                        if web_el: website = web_el.get_attribute('href')
                    except: pass
                        
                    if website and "http" in website:
                        headers = {'User-Agent': 'Mozilla/5.0'}
                        try:
                            res = requests.get(website, headers=headers, timeout=8)
                            emails = extraer_emails(res.text)
                            
                            if not emails:
                                soup = BeautifulSoup(res.text, 'html.parser')
                                for a in soup.find_all('a', href=True):
                                    if any(x in a.text.lower() for x in ['contact', 'contacto']):
                                        c_url = urllib.parse.urljoin(website, a['href'])
                                        res_c = requests.get(c_url, headers=headers, timeout=5)
                                        emails = extraer_emails(res_c.text)
                                        if emails: break
                                        
                            if emails:
                                target_email = emails[0].lower().strip()
                                
                                # Verificar si ya existe en la Base de Datos
                                with db_lock:
                                    existe = db.query(Lead).filter(Lead.email == target_email).first()
                                
                                if not existe:
                                    wlog(f"[SCOUT] 🎯 CAZADO: {target_email} ({nombre}) -> Guardado como PENDIENTE")
                                    
                                    # Guardar en DB con la query en source
                                    nuevo_lead = Lead(
                                        email=target_email,
                                        name="Equipo",
                                        company=nombre,
                                        source=f"google_maps: {current_query}",
                                        status="pending"
                                    )
                                    with db_lock:
                                        db.add(nuevo_lead)
                                        db.commit()
                                    leads_scraped_current_run += 1
                                else:
                                    print(f"[SCOUT] [DEBUG] Duplicado: {target_email} ya existe en base de datos.")
                            else:
                                print(f"[SCOUT] [DEBUG] Sin email público visible en {website}")
                        except Exception as web_ex:
                            print(f"[SCOUT] [DEBUG] Web caída o bloqueada {website}: {web_ex}")
                    else:
                        print(f"[SCOUT] [DEBUG] {nombre} no tiene sitio web público.")
                    
                    # Registrar negocio como procesado para evitar visitas duplicadas en el futuro
                    if nombre != "Empresa":
                        with db_lock:
                            existe_db_proc = db.query(ProcessedBusiness).filter(ProcessedBusiness.company_name == nombre).first()
                            if not existe_db_proc:
                                nuevo_proc = ProcessedBusiness(company_name=nombre)
                                db.add(nuevo_proc)
                                db.commit()
                                
                except Exception as e:
                    print(f"[SCOUT] [DEBUG] Error al procesar elemento {i}: {e}")
                
        browser.close()
        db.close()
        
    campaign_state["is_running"] = False
    wlog(f"[SCOUT] 🎉 CAMPAÑA FINALIZADA. Se recolectaron {leads_scraped_current_run} nuevos prospectos en total.")
