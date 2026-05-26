import os
import glob
from logger import wlog

def get_hq_path():
    desktop_hq = "/Users/jereganza/Desktop/Egasis_HQ"
    try:
        os.makedirs(desktop_hq, exist_ok=True)
    except Exception:
        desktop_hq = os.path.abspath(os.path.join(os.path.dirname(__file__), "Egasis_HQ"))
        os.makedirs(desktop_hq, exist_ok=True)
    return desktop_hq

HQ_PATH = get_hq_path()
LEADS_DIR = os.path.join(HQ_PATH, "1_Leads")
PROYECTOS_DIR = os.path.join(HQ_PATH, "4_Proyectos")

def create_project_base(company_name):
    # Crear carpeta del cliente
    folder_name = company_name.replace(" ", "_").replace("/", "")
    project_path = os.path.join(PROYECTOS_DIR, folder_name)
    os.makedirs(project_path, exist_ok=True)
    
    # Crear subcarpetas
    os.makedirs(os.path.join(project_path, "n8n_workflows"), exist_ok=True)
    os.makedirs(os.path.join(project_path, "scripts"), exist_ok=True)
    
    # Crear README
    with open(os.path.join(project_path, "README.md"), "w", encoding="utf-8") as f:
        f.write(f"# Proyecto de Automatización para {company_name}\n\n")
        f.write("## 1. Arquitectura\n")
        f.write("- **n8n**: Flujos de mensajería y agendamiento.\n")
        f.write("- **OpenAI/Gemini**: Cerebro de respuestas.\n\n")
        f.write("## 2. Tareas de Implementación\n")
        f.write("- [ ] Diseñar flujo principal.\n")
        f.write("- [ ] Conectar API de WhatsApp.\n")
        f.write("- [ ] Entrenar IA con los datos de la clínica.\n")

    # Crear script de demo básico
    with open(os.path.join(project_path, "scripts", "demo_chat.py"), "w", encoding="utf-8") as f:
        f.write(f'# Demo Chatbot para {company_name}\n')
        f.write('print("Hola! Soy el asistente virtual de ' + company_name + '")\n')
        f.write('print("¿En qué te puedo ayudar hoy?")\n')

def check_preparados():
    print("💻 [Agente Desarrollador] Buscando leads preparados...")
    for filepath in glob.glob(os.path.join(LEADS_DIR, "*.md")):
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
            
        if "status: preparado" in content:
            # Extraer info
            company = ""
            for line in content.splitlines():
                if line.startswith("company:"): company = line.replace("company:", "").strip()
                
            print(f"   => Construyendo base de proyecto para: {company}")
            create_project_base(company)
            print(f"      ✅ Base de código generada en 4_Proyectos/{company.replace(' ', '_')}/")
            
            # 3. Actualizar status a "desarrollado" o "listo"
            content = content.replace("status: preparado", "status: listo_para_demo")
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)

if __name__ == "__main__":
    check_preparados()
