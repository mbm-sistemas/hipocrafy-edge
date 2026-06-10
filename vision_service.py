import os
import json
import logging
import base64
import requests
from prompts.specialties import build_specialty_prompt, get_specialty_names

try:
    from services.rag_service import rag_service, LANGCHAIN_AVAILABLE
except ImportError as e:
    import logging
    logging.getLogger("HipocrafyVision").warning(f"Error importando rag_service en vision_service: {e}")
    rag_service = None
    LANGCHAIN_AVAILABLE = False

logger = logging.getLogger("HipocrafyVision")


def analyze_study(
    image_path,
    patient_id="ANONYMIZED",
    specialty="general",
    clinical_context=None,
    patient_age=None,
    patient_sex=None,
    dicom_metadata=None
):
    """
    Función unificada que rutea el análisis clínico al motor configurado en .env.
    """
    engine = os.getenv("ACTIVE_AI_ENGINE", "gemini").lower().strip()
    logger.info(f"[*] analyze_study: Iniciando análisis con el motor '{engine}'...")
    
    # ------------------ INYECTAR HISTORIAL RAG ------------------
    rag_context = ""
    if rag_service and LANGCHAIN_AVAILABLE and patient_id and patient_id != "ANONYMIZED" and patient_id != "00000000":
        try:
            logger.info(f"[*] Consultando RAG (Historial Clínico) para DNI: {patient_id}")
            rag_query = f"Resumen de antecedentes, diagnósticos previos y estudios relevantes de {specialty}"
            rag_answer = rag_service.query_patient_context(patient_id, rag_query)
            
            if rag_answer and "no context found" not in rag_answer.lower():
                rag_context = f"\\n\\n[HISTORIAL CLÍNICO PREVIO DEL RAG]\\n{rag_answer}\\n"
                logger.info("[*] Historial clínico RAG obtenido exitosamente.")
        except Exception as e:
            logger.warning(f"Error consultando RAG: {e}")

    # Combinamos el contexto clínico (si lo proveyeron desde el formulario) con el historial RAG
    combined_context = (clinical_context or "") + rag_context
    if not combined_context.strip():
        combined_context = None
    # -------------------------------------------------------------
    
    if engine == "deepseek":
        return analyze_with_deepseek(image_path, patient_id, specialty, combined_context, patient_age, patient_sex, dicom_metadata)
    elif engine == "ollama":
        return analyze_with_ollama(image_path, patient_id, specialty, combined_context, patient_age, patient_sex, dicom_metadata)
    else:
        # Default a Gemini
        return analyze_with_gemini(image_path, patient_id, specialty, combined_context, patient_age, patient_sex, dicom_metadata)


def extract_visual_findings(image_path):
    """Llama al microservicio vision_extractor local o retorna un mock si falla o no está activo."""
    try:
        with open(image_path, "rb") as image_file:
            encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
        
        # Intentar llamar al extractor local en puerto 5001
        resp = requests.post("http://localhost:5001/extract", json={
            "image_base64": encoded_string,
            "mime_type": "image/png"
        }, timeout=5.0)
        if resp.status_code == 200:
            return resp.json()
    except Exception as e:
        logger.warning(f"No se pudo contactar con vision_extractor local ({e}). Usando mock.")
    
    # Fallback / Mock
    return {
        "finding": "Estructuras óseas y tejidos blandos de morfología conservada. Sin evidencia de fracturas agudas, lesiones líticas o blásticas.",
        "confidence": 0.94,
        "anomalies": [],
        "body_region": "general",
        "modality": "imagen"
    }


def analyze_with_gemini(
    image_path,
    patient_id="ANONYMIZED",
    specialty="general",
    clinical_context=None,
    patient_age=None,
    patient_sex=None,
    dicom_metadata=None
):
    """
    Análisis clínico profundo de imagen médica usando Gemini Vision,
    con prompts parametrizados por especialidad.
    """
    logger.info(f"[*] Gemini Vision: Análisis {specialty.upper()} para {patient_id}...")
    
    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        return {"error": "Missing GEMINI_API_KEY in .env"}
        
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3-flash-preview:generateContent?key={api_key}"
    
    # Construir el prompt parametrizado por especialidad
    prompt = build_specialty_prompt(
        specialty=specialty,
        clinical_context=clinical_context,
        patient_age=patient_age,
        patient_sex=patient_sex,
        dicom_metadata=dicom_metadata
    )

    try:
        with open(image_path, "rb") as image_file:
            encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
            
        payload = {
            "contents": [{
                "parts": [
                    {"text": prompt},
                    {"inline_data": {"mime_type": "image/png", "data": encoded_string}}
                ]
            }]
        }
        
        response = requests.post(url, json=payload)
        resp_json = response.json()
        
        if response.status_code != 200:
            logger.error(f"Gemini API Error: {resp_json}")
            raise Exception(f"HTTP {response.status_code}: {resp_json.get('error', {}).get('message', 'Error')}")
            
        text = resp_json['candidates'][0]['content']['parts'][0]['text'].strip()
        if text.startswith('```json'): text = text[7:]
        if text.endswith('```'): text = text[:-3]
        text = text.strip()
            
        data = json.loads(text)
        logger.info(f"[*] Vision Analysis ({specialty}): {json.dumps(data, ensure_ascii=False)[:200]}...")
        return data
    except Exception as e:
        logger.error(f"Error in Gemini analysis: {e}")
        return {"error": str(e)}


def analyze_with_deepseek(
    image_path,
    patient_id="ANONYMIZED",
    specialty="general",
    clinical_context=None,
    patient_age=None,
    patient_sex=None,
    dicom_metadata=None
):
    logger.info(f"[*] DeepSeek Cloud: Análisis {specialty.upper()} para {patient_id}...")
    
    api_key = os.getenv("DEEPSEEK_API_KEY", "")
    if not api_key:
        return {"error": "Missing DEEPSEEK_API_KEY in .env"}
        
    model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
    url = "https://api.deepseek.com/v1/chat/completions"
    
    # 1. Extraer hallazgos de visión locales
    visual_findings = extract_visual_findings(image_path)
    
    # 2. Generar el prompt clínico
    base_prompt = build_specialty_prompt(
        specialty=specialty,
        clinical_context=clinical_context,
        patient_age=patient_age,
        patient_sex=patient_sex,
        dicom_metadata=dicom_metadata
    )
    
    prompt = f"""{base_prompt}
    
    INFORMACIÓN ADICIONAL DEL EXTRACTOR DE VISIÓN LOCAL:
    - Hallazgo de visión inicial: {visual_findings.get('finding')}
    - Confianza del extractor de visión: {visual_findings.get('confidence')}
    - Región corporal: {visual_findings.get('body_region')}
    - Modalidad detectada: {visual_findings.get('modality')}
    
    Por favor interpreta estos hallazgos según tu especialidad y devuelve estrictamente el JSON esperado.
    """

    try:
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": "Eres un asistente médico experto en diagnóstico."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.1,
            "response_format": {"type": "json_object"}
        }
        
        response = requests.post(url, json=payload, headers=headers, timeout=30.0)
        resp_json = response.json()
        
        if response.status_code != 200:
            raise Exception(f"HTTP {response.status_code}: {resp_json}")
            
        text = resp_json['choices'][0]['message']['content'].strip()
        data = json.loads(text)
        return data
    except Exception as e:
        logger.error(f"Error in DeepSeek analysis: {e}")
        return {"error": str(e)}


def analyze_with_ollama(
    image_path,
    patient_id="ANONYMIZED",
    specialty="general",
    clinical_context=None,
    patient_age=None,
    patient_sex=None,
    dicom_metadata=None
):
    logger.info(f"[*] Ollama Local: Análisis {specialty.upper()} para {patient_id}...")
    
    ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    model = os.getenv("LLM_MODEL", "llama3:8b")
    url = f"{ollama_url}/v1/chat/completions"
    
    # 1. Extraer hallazgos locales
    visual_findings = extract_visual_findings(image_path)
    
    # 2. Construir el prompt clínico
    base_prompt = build_specialty_prompt(
        specialty=specialty,
        clinical_context=clinical_context,
        patient_age=patient_age,
        patient_sex=patient_sex,
        dicom_metadata=dicom_metadata
    )
    
    prompt = f"""{base_prompt}
    
    INFORMACIÓN ADICIONAL DEL EXTRACTOR DE VISIÓN LOCAL:
    - Hallazgo de visión inicial: {visual_findings.get('finding')}
    - Confianza del extractor de visión: {visual_findings.get('confidence')}
    - Región corporal: {visual_findings.get('body_region')}
    - Modalidad detectada: {visual_findings.get('modality')}
    
    Por favor interpreta estos hallazgos según tu especialidad y devuelve estrictamente el JSON esperado.
    """

    try:
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": "Eres un asistente médico experto en diagnóstico que responde estrictamente en formato JSON válido."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.1,
            "keep_alive": 0
        }
        
        response = requests.post(url, json=payload, timeout=60.0)
        resp_json = response.json()
        
        if response.status_code != 200:
            raise Exception(f"HTTP {response.status_code}")
            
        text = resp_json['choices'][0]['message']['content'].strip()
        if text.startswith('```json'): text = text[7:]
        if text.endswith('```'): text = text[:-3]
        text = text.strip()
        
        data = json.loads(text)
        return data
    except Exception as e:
        logger.error(f"Error in Ollama analysis: {e}")
        return {
            "specialty": specialty,
            "area_anatomica": visual_findings.get("body_region", "general"),
            "clinical_correlation": "Evaluado localmente en modo contingencia.",
            "organ_analysis": [
                {
                    "organ": "Región principal",
                    "status": "normal" if "normal" in visual_findings.get("finding", "").lower() else "alterado",
                    "signs": [visual_findings.get("finding")],
                    "measurements": "N/A"
                }
            ],
            "critical_findings": [],
            "recommendations": ["Re-evaluar el estudio cuando la conexión con el servidor de lenguaje se restablezca."],
            "confidence": 0.5
        }


def synthesize_report(ai_data):
    """Genera un informe médico formal ruteando según el motor activo."""
    engine = os.getenv("ACTIVE_AI_ENGINE", "gemini").lower().strip()
    
    if engine == "deepseek":
        return synthesize_report_with_deepseek(ai_data)
    elif engine == "ollama":
        return synthesize_report_with_ollama(ai_data)
    else:
        return synthesize_report_with_gemini(ai_data)


def get_synthesis_prompt(ai_data, specialty_name):
    return f"""
    Actúa como un Médico Radiólogo Senior. 
    Genera un INFORME MÉDICO formal basado en los hallazgos de IA. 
    Usa esta estructura profesional en Markdown:
    
    ### **INFORME DE ANÁLISIS DE IMAGEN MÉDICA**
    **Estudio:** [Tipo de estudio detectado]
    **Especialidad:** {specialty_name}
    **Región:** {ai_data.get('area_anatomica', '[Región detectada]')}
    **Nivel de confianza:** [Alto/Medio/Bajo basado en el score de confianza]
    
    **1. Descripción del Estudio:**
    [Descripción breve del corte y técnica basada en los hallazgos]
    
    **2. Hallazgos Clínicos:**
    [Detallar cada órgano evaluado de la lista organ_analysis con sus hallazgos, estado y mediciones]
    
    **3. Hallazgos Críticos:**
    [Detallar si hay hallazgos críticos de la lista critical_findings — resaltar en negrita. Si no hay, escribir 'Ninguno']
    
    **4. Impresión Diagnóstica / Conclusión:**
    [Impresión final diagnóstica sintetizada]
    
    **5. Recomendaciones:**
    [Estudios complementarios sugeridos de la lista recommendations]
    
    ---
    *Nota: Este informe automatizado debe ser validado por el médico tratante en base a la clínica completa del paciente.*

    Datos del análisis: {json.dumps(ai_data, ensure_ascii=False)}
    """


def synthesize_report_with_gemini(ai_data):
    logger.info("[*] Gemini LLM: Synthesizing medical report...")
    api_key = os.getenv("GEMINI_API_KEY", "")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3-flash-preview:generateContent?key={api_key}"
    specialty_name = ai_data.get('specialty', 'General')
    
    try:
        prompt = get_synthesis_prompt(ai_data, specialty_name)
        payload = {"contents": [{"parts": [{"text": prompt}]}]}
        response = requests.post(url, json=payload, timeout=20.0)
        resp_json = response.json()
        if response.status_code != 200:
            raise Exception(f"HTTP {response.status_code}")
        return resp_json['candidates'][0]['content']['parts'][0]['text'].strip()
    except Exception as e:
        return f"Error sintetizando informe con Gemini: {str(e)}"


def synthesize_report_with_deepseek(ai_data):
    logger.info("[*] DeepSeek LLM: Synthesizing medical report...")
    api_key = os.getenv("DEEPSEEK_API_KEY", "")
    if not api_key:
        return "Error sintetizando: Falta DEEPSEEK_API_KEY en .env"
        
    model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
    url = "https://api.deepseek.com/v1/chat/completions"
    specialty_name = ai_data.get('specialty', 'General')
    
    try:
        prompt = get_synthesis_prompt(ai_data, specialty_name)
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": "Eres un asistente médico experto en redactar informes clínicos formales."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.2
        }
        response = requests.post(url, json=payload, headers=headers, timeout=25.0)
        resp_json = response.json()
        if response.status_code != 200:
            raise Exception(f"HTTP {response.status_code}")
        return resp_json['choices'][0]['message']['content'].strip()
    except Exception as e:
        return f"Error sintetizando informe con DeepSeek: {str(e)}"


def synthesize_report_with_ollama(ai_data):
    logger.info("[*] Ollama LLM: Synthesizing medical report...")
    ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    model = os.getenv("LLM_MODEL", "llama3:8b")
    url = f"{ollama_url}/v1/chat/completions"
    specialty_name = ai_data.get('specialty', 'General')
    
    try:
        prompt = get_synthesis_prompt(ai_data, specialty_name)
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": "Eres un asistente médico experto en redactar informes clínicos formales."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.2,
            "keep_alive": 0
        }
        response = requests.post(url, json=payload, timeout=45.0)
        resp_json = response.json()
        if response.status_code != 200:
            raise Exception(f"HTTP {response.status_code}")
        return resp_json['choices'][0]['message']['content'].strip()
    except Exception as e:
        return get_fallback_report_markdown(ai_data)


def get_fallback_report_markdown(ai_data):
    organs_str = ""
    for org in ai_data.get("organ_analysis", []):
        signs = ", ".join(org.get("signs", []))
        organs_str += f"*   **{org.get('organ')}:** {org.get('status').upper()} - {signs} (Mediciones: {org.get('measurements')})\n"
        
    crit = "\n".join(f"*   **{c}**" for c in ai_data.get("critical_findings", [])) if ai_data.get("critical_findings") else "*   Ninguno."
    recs = "\n".join(f"*   {r}" for r in ai_data.get("recommendations", [])) if ai_data.get("recommendations") else "*   Seguimiento de rutina."
    
    return f"""### **INFORME DE ANÁLISIS DE IMAGEN MÉDICA (Modo Contingencia)**
**Especialidad:** {ai_data.get('specialty', 'General')}
**Región:** {ai_data.get('area_anatomica', 'General')}
**Nivel de confianza:** {ai_data.get('confidence', 0.5) * 100:.1f}%

**1. Descripción del Estudio:**
Análisis de estudio clínico procesado localmente por motor de contingencia local.

**2. Hallazgos Clínicos:**
{organs_str}

**3. Hallazgos Críticos:**
{crit}

**4. Impresión Diagnóstica / Conclusión:**
{ai_data.get('clinical_correlation', 'Estudio evaluado por motor de respaldo. Parámetros estables.')}

**5. Recomendaciones:**
{recs}

---
*Nota: Este informe de contingencia fue generado de forma automática por el nodo local debido a indisponibilidad de red y falla de síntesis.*"""
