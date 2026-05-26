import os
import time
from scraper import run_scraper
from logger import wlog

def get_hq_path():
    desktop_hq = "/Users/jereganza/Desktop/Egasis_HQ"
    try:
        os.makedirs(desktop_hq, exist_ok=True)
    except Exception:
        desktop_hq = os.path.abspath(os.path.join(os.path.dirname(__file__), "Egasis_HQ"))
        os.makedirs(desktop_hq, exist_ok=True)
    return desktop_hq

def read_strategy():
    hq_path = get_hq_path()
    strategy_file = os.path.join(hq_path, "5_Cerebro_Central/Estrategia_Busqueda.md")
    queries = []
    
    # 1. Intentar leer desde el archivo si existe
    if os.path.exists(strategy_file):
        try:
            with open(strategy_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("- "):
                        queries.append(line[2:].strip())
            if queries:
                return queries
        except Exception as e:
            wlog(f"⚠️ [Agente Scout] Error al leer Estrategia_Busqueda.md: {e}")
            
    # 2. Si no existe o está vacío, consultar la base de datos (outreach.db)
    wlog("🕵️‍♂️ [Agente Scout] Buscando cola de búsqueda en la Base de Datos...")
    try:
        from database import SessionLocal, get_setting
        db = SessionLocal()
        db_queue = get_setting(db, "search_queue", "")
        db.close()
        if db_queue:
            queries = [q.strip() for q in db_queue.split("\n") if q.strip()]
    except Exception as e:
        wlog(f"⚠️ [Agente Scout] Error al consultar base de datos: {e}")
        
    # 3. Fallback final por defecto
    if not queries:
        queries = [
            "Agencias de marketing en Madrid",
            "Agencias SEO en Barcelona",
            "Desarrolladores web en Valencia"
        ]
        
    # 4. Intentar guardar de vuelta en Estrategia_Busqueda.md para sincronización y portabilidad
    dir_path = os.path.dirname(strategy_file)
    try:
        os.makedirs(dir_path, exist_ok=True)
        with open(strategy_file, "w", encoding="utf-8") as f:
            f.write("# Estrategia de Búsqueda Autónoma\n\n")
            f.write("Lista de consultas configurada por Egasis Studio:\n\n")
            for q in queries:
                f.write(f"- {q}\n")
        wlog(f"📝 [Agente Scout] Archivo Obsidian sincronizado en: {strategy_file}")
    except Exception as e:
        wlog(f"⚠️ [Agente Scout] No se pudo crear o actualizar el archivo de Obsidian: {e}")
            
    return queries

def auto_scout_loop():
    wlog("🕵️‍♂️ [Agente Scout] Iniciando modo autónomo.")
    while True:
        try:
            queries = read_strategy()
            if not queries:
                wlog("🕵️‍♂️ [Agente Scout] No hay queries en Estrategia_Busqueda.md. Durmiendo 1 hora.")
                time.sleep(3600)
                continue
                
            wlog(f"🕵️‍♂️ [Agente Scout] Leídas {len(queries)} búsquedas desde Obsidian. Iniciando prospección...")
            queries_str = ",".join(queries)
            
            # Llamamos al scraper central
            run_scraper(queries_str, max_results=50)
            
            wlog("🕵️‍♂️ [Agente Scout] Ciclo finalizado. Durmiendo 24 horas hasta la próxima búsqueda automática.")
            # Duerme 24 horas (86400 segundos)
            time.sleep(86400)
            
        except Exception as e:
            wlog(f"🕵️‍♂️ [Agente Scout] Error crítico: {e}. Reintentando en 5 minutos...")
            time.sleep(300)

if __name__ == "__main__":
    auto_scout_loop()
