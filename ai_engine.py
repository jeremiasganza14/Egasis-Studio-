import re
import random
import os
from dotenv import load_dotenv

load_dotenv()

AI_PROVIDER = os.getenv("AI_PROVIDER", "gemini").lower()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

def process_spintax(text: str) -> str:
    """Procesa spintax básico ej. {Hola|Estimado|Qué tal}."""
    pattern = re.compile(r'\{([^{}]*)\}')
    while True:
        match = pattern.search(text)
        if not match:
            break
        options = match.group(1).split('|')
        choice = random.choice(options)
        text = text[:match.start()] + choice + text[match.end():]
    return text

def _call_gemini(prompt: str) -> str:
    try:
        from google import genai
        client = genai.Client(api_key=GEMINI_API_KEY)
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
        )
        return response.text
    except Exception as e:
        print(f"Error calling Gemini: {e}")
        return ""

def _call_openai(prompt: str) -> str:
    try:
        from openai import OpenAI
        client = OpenAI(api_key=OPENAI_API_KEY)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=150
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"Error calling OpenAI: {e}")
        return ""

def extract_learning_from_reply(reply_body: str, company: str, classification: str) -> str:
    """Usa IA para extraer una lección de ventas de la respuesta del prospecto."""
    prompt = f"""
    Eres un analista de ventas B2B. Acabamos de recibir una respuesta de la empresa {company}.
    La respuesta ha sido clasificada como: {classification}.
    
    Respuesta del cliente:
    "{reply_body}"
    
    Extrae UNA conclusión o lección comercial (máximo 2 líneas) que podamos aprender de esto para mejorar nuestros futuros correos en frío. 
    Ejemplo si es negativa: "Las clínicas rechazan por precio, probar ángulo de prueba gratuita."
    Ejemplo si es positiva: "Aprecian que mencione la integración con WhatsApp. Mantener este foco."
    """
    res = ""
    if AI_PROVIDER == "openai" and OPENAI_API_KEY:
        res = _call_openai(prompt)
    elif AI_PROVIDER == "gemini" and GEMINI_API_KEY:
        res = _call_gemini(prompt)
    return res.strip() if res else ""

def generate_ai_variant(base_template: str, company_name: str, contact_name: str, past_learnings: list = None) -> str:
    """Usa IA para reescribir la plantilla sutilmente para que suene natural, 
    sin cambiar el sentido original ni agregar relleno extra."""
    
    # 1. Reemplazar variables primero para evitar que la IA rompa las llaves {}
    texto_personalizado = base_template.replace("{Nombre}", contact_name).replace("{Empresa}", company_name)
    texto_personalizado = process_spintax(texto_personalizado)
    
    learnings_text = ""
    if past_learnings and len(past_learnings) > 0:
        learnings_text = "Ten en cuenta estas lecciones de ventas aprendidas de correos anteriores para mejorar la persuasión de este nuevo correo:\n"
        for l in past_learnings:
            learnings_text += f"- {l}\n"
    
    prompt = f"""
    Reescribe sutilmente el siguiente correo de prospección B2B. 
    Mantenlo breve, directo, profesional pero amigable. NO agregues firmas falsas.
    NO inventes servicios que no ofrezco. 
    El correo va dirigido a {contact_name} de la empresa {company_name}. Asegúrate de usar estos nombres reales en la reescritura.
    Mantén el formato HTML básico si lo tiene.
    
    {learnings_text}
    
    Correo original:
    {texto_personalizado}
    
    Reescritura:
    """
    
    if AI_PROVIDER == "openai" and OPENAI_API_KEY:
        res = _call_openai(prompt)
    elif AI_PROVIDER == "gemini" and GEMINI_API_KEY:
        res = _call_gemini(prompt)
    else:
        res = texto_personalizado
        
    if not res:
        res = texto_personalizado
        
    return res

def classify_reply(email_body: str) -> tuple[str, str]:
    """
    Clasifica la respuesta de un cliente de forma robusta.
    Retorna (classification, priority).
    Classification: interested, not_interested, unsubscribe, out_of_office, info_requested, spam, unclassified
    Priority: high, medium, low
    """
    prompt = f"""
    Analiza este correo de respuesta de un prospecto B2B y clasifícalo en UNA de estas categorías:
    - interested (Muestra interés explícito o implícito, acepta una llamada, pide agendar, dice "hablemos más adelante", etc.)
    - info_requested (Pide más información, catálogo, dossier, precios, detalles del servicio o pregunta qué hacemos antes de coordinar llamada)
    - not_interested (Rechaza la propuesta de manera cortés o neutral, dice "no gracias", "ya tenemos proveedor", "no lo necesitamos por ahora")
    - unsubscribe (Exige explícitamente ser borrado de la lista, pide que no lo contacten más, dice "remover", "dar de baja", "baja", "borrar de la base de datos", "unsubscribe", o muestra enojo por ser contactado)
    - out_of_office (Respuesta automática o manual indicando ausencia temporal, vacaciones, fuera de la oficina, o que responderán a su regreso)
    - spam (Correos comerciales no solicitados, publicidad, promociones, boletines informativos, o errores de entrega del servidor)
    - unclassified (Mensajes ambiguos que no encajan en ninguna de las anteriores)
    
    Determina también la prioridad para el seguimiento:
    - high: para interesados (interested) o solicitudes claras de información (info_requested).
    - low: para rechazos (not_interested), bajas (unsubscribe), spam, o respuestas automáticas (out_of_office).
    - medium: si el correo es ambiguo o no entra exactamente en las anteriores.

    INSTRUCCIÓN DE FORMATO CRÍTICA:
    Devuelve ÚNICAMENTE dos palabras separadas por una coma en minúsculas, sin puntuación adicional, sin comillas, sin bloques de código, sin texto introductorio ni explicaciones.
    Ejemplo exacto de respuesta válida:
    interested,high

    Correo a analizar:
    "{email_body}"
    """
    
    res = ""
    if AI_PROVIDER == "openai" and OPENAI_API_KEY:
        res = _call_openai(prompt)
    elif AI_PROVIDER == "gemini" and GEMINI_API_KEY:
        res = _call_gemini(prompt)
        
    # Limpieza robusta de la respuesta de la IA
    if res:
        res = res.strip().lower()
        # Eliminar bloques de código markdown si los hay
        res = re.sub(r'```[a-z]*', '', res).strip()
        # Eliminar caracteres como comillas, corchetes, etc.
        res = res.replace('"', '').replace("'", "").replace("[", "").replace("]", "").strip()
        # Extraer primera y segunda palabra limpia dividida por coma
        try:
            # Buscar una estructura palabra,palabra usando regex
            match = re.search(r'([a-z_]+)\s*,\s*([a-z_]+)', res)
            if match:
                clsf = match.group(1).strip()
                prio = match.group(2).strip()
            else:
                parts = [p.strip() for p in res.split(',') if p.strip()]
                clsf = parts[0] if len(parts) > 0 else "unclassified"
                prio = parts[1] if len(parts) > 1 else "medium"
                
            valid_clsf = ["interested", "not_interested", "unsubscribe", "out_of_office", "info_requested", "spam", "unclassified"]
            valid_prio = ["high", "medium", "low"]
            
            if clsf not in valid_clsf: 
                # Intentar mapear variaciones comunes
                if "interested" in clsf: clsf = "interested"
                elif "unsubscribe" in clsf or "baja" in clsf or "remove" in clsf or "contact" in clsf: clsf = "unsubscribe"
                elif "not" in clsf: clsf = "not_interested"
                elif "office" in clsf or "out" in clsf: clsf = "out_of_office"
                elif "info" in clsf: clsf = "info_requested"
                elif "spam" in clsf: clsf = "spam"
                else: clsf = "unclassified"
                
            if prio not in valid_prio: 
                if "high" in prio: prio = "high"
                elif "low" in prio: prio = "low"
                else: prio = "medium"
                
            return clsf, prio
        except Exception:
            pass
            
    # Fallback básico basado en regex y palabras clave si falla la IA
    body_lower = email_body.lower()
    if any(x in body_lower for x in ["remover", "unsubscribe", "baja", "borrar", "no contactar", "no escribir", "no me interesa recibir", "lista negra", "delete"]):
        return "unsubscribe", "low"
    if any(x in body_lower for x in ["no me interesa", "no gracias", "no estoy interesado", "no nos interesa", "ya tenemos"]):
        return "not_interested", "low"
    if any(x in body_lower for x in ["fuera de la oficina", "out of office", "vacaciones", "ausente", "responderé a mi regreso"]):
        return "out_of_office", "low"
    if any(x in body_lower for x in ["más info", "precios", "dossier", "catalogo", "tarifa", "de qué se trata", "información", "en qué consiste", "precios"]):
        return "info_requested", "high"
    if any(x in body_lower for x in ["reunión", "llamada", "hablemos", "me interesa", "agendar", "agenda", "de acuerdo", "dale"]):
        return "interested", "high"
    if any(x in body_lower for x in ["buy now", "click here", "newsletter", "publicidad", "oferta"]):
        return "spam", "low"
        
    return "unclassified", "medium"
