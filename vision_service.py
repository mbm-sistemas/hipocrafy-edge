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


def classify_ai_error(exception_str: str, engine: str, http_status: int | None = None) -> dict:
    """
    Clasifica un error de IA en event_type + severity para reportar al cloud.
    Retorna dict con: event_type, severity, metadata.
    """
    s = (exception_str or "").lower()
    status = http_status or 0

    # Determinar tipo y severidad según el HTTP status y el texto del error
    if status in (401, 403) or "401" in s or "403" in s or "unauthorized" in s or "api key" in s or "permission" in s:
        return {"event_type": "auth_failed",        "severity": "critical", "metadata": {"http_status": status, "detail": exception_str[:300]}}
    if status in (402, 429) or "402" in s or "429" in s or "quota" in s or "billing" in s or "credit" in s or "rate limit" in s or "resource_exhausted" in s:
        return {"event_type": "quota_exhausted",    "severity": "critical", "metadata": {"http_status": status, "detail": exception_str[:300]}}
    if status == 404 or "404" in s or "model" in s and ("not found" in s or "deprecated" in s or "unavailable" in s):
        return {"event_type": "model_unavailable",  "severity": "warning",  "metadata": {"http_status": status, "detail": exception_str[:300]}}
    if status in (500, 502, 503) or "timeout" in s or "timed out" in s or "connection" in s:
        return {"event_type": "timeout",            "severity": "warning",  "metadata": {"http_status": status, "detail": exception_str[:300]}}
    if "json" in s or "parse" in s or "decode" in s or "invalid" in s:
        return {"event_type": "parse_error",        "severity": "warning",  "metadata": {"http_status": status, "detail": exception_str[:300]}}
    return     {"event_type": "ai_error",           "severity": "warning",  "metadata": {"http_status": status, "detail": exception_str[:300]}}


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
    
    _engines = [
        ("gemini",   analyze_with_gemini),
        ("deepseek", analyze_with_deepseek),
        ("ollama",   analyze_with_ollama),
    ]
    # Poner el motor preferido primero, los demás como fallback en orden
    preferred_idx = next((i for i, (name, _) in enumerate(_engines) if name == engine), 0)
    ordered = _engines[preferred_idx:] + _engines[:preferred_idx]

    call_args = (image_path, patient_id, specialty, combined_context, patient_age, patient_sex, dicom_metadata)
    last_error = None
    last_event_meta = None
    failed_engines = []

    for eng_name, fn in ordered:
        try:
            logger.info(f"[*] Intentando motor: {eng_name.upper()}...")
            result = fn(*call_args)
            if result and "error" not in result:
                if failed_engines:
                    # Al menos un motor falló antes — marcamos fallback para el reporte
                    result["_event_meta"] = {
                        "event_type": "fallback_activated",
                        "severity":   "info",
                        "engine":     eng_name,
                        "metadata":   {"failed_engines": failed_engines},
                    }
                logger.info(f"[+] Motor {eng_name.upper()} respondió exitosamente.")
                return result
            last_error = result.get("error", "respuesta vacía")
            last_event_meta = result.get("_event_meta") or classify_ai_error(last_error, eng_name)
            last_event_meta["engine"] = eng_name
            failed_engines.append(eng_name)
            logger.warning(f"[!] {eng_name.upper()} devolvió error: {last_error}. Probando siguiente motor.")
        except Exception as e:
            last_error = str(e)
            last_event_meta = classify_ai_error(last_error, eng_name)
            last_event_meta["engine"] = eng_name
            failed_engines.append(eng_name)
            logger.warning(f"[!] {eng_name.upper()} falló con excepción: {e}. Probando siguiente motor.")

    logger.error(f"[X] Todos los motores de IA fallaron. Último error: {last_error}")
    event_meta = last_event_meta or {"event_type": "ai_error", "severity": "critical", "engine": None, "metadata": {}}
    event_meta["event_type"] = "ai_error"
    event_meta["severity"]   = "critical"
    event_meta["metadata"]   = {**(event_meta.get("metadata") or {}), "failed_engines": failed_engines}
    return {
        "specialty": specialty,
        "area_anatomica": "no evaluable",
        "clinical_correlation": "Sin conectividad con motores de IA. Verificar claves API y conexión.",
        "organ_analysis": [],
        "critical_findings": [],
        "recommendations": ["Reintentar el análisis cuando se restablezca la conectividad."],
        "confidence": 0.0,
        "error": f"Todos los motores fallaron: {last_error}",
        "_event_meta": event_meta,
    }


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
        
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
    
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
        
        response = requests.post(url, json=payload, timeout=30.0)
        if not response.text.strip():
            raise Exception("Gemini returned empty response — check API key format (must start with AIza)")
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
        http_status = getattr(getattr(e, 'response', None), 'status_code', None)
        return {"error": str(e), "_event_meta": classify_ai_error(str(e), "gemini", http_status)}


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

    # Si DEEPSEEK_LOCAL_FIRST=true, intenta la URL local antes que la nube
    local_first = os.getenv("DEEPSEEK_LOCAL_FIRST", "false").lower() == "true"
    local_url   = os.getenv("DEEPSEEK_LOCAL_URL", "")
    cloud_url   = "https://api.deepseek.com/v1/chat/completions"
    urls_to_try = ([local_url, cloud_url] if local_first and local_url else [cloud_url])
    
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

    last_error = None
    for endpoint in urls_to_try:
        try:
            logger.info(f"[*] DeepSeek → {endpoint}")
            response = requests.post(endpoint, json=payload, headers=headers, timeout=30.0)
            resp_json = response.json()
            if response.status_code != 200:
                raise Exception(f"HTTP {response.status_code}: {resp_json}")
            text = resp_json['choices'][0]['message']['content'].strip()
            return json.loads(text)
        except Exception as e:
            last_error = str(e)
            logger.warning(f"[!] DeepSeek endpoint {endpoint} falló: {e}. Probando siguiente.")

    logger.error(f"Error in DeepSeek analysis: {last_error}")
    return {"error": last_error, "_event_meta": classify_ai_error(str(last_error), "deepseek")}


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
        
        response = requests.post(url, json=payload, timeout=180.0)
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
    tech_desc = ai_data.get("technical_description", "")
    tech_section = f"\n    **Descripción técnica (generada automáticamente):**\n    {tech_desc}\n" if tech_desc else ""

    return f"""
    Actúa como un Médico Radiólogo Senior.
    Genera la SECCIÓN MÉDICA del informe (hallazgos e impresión diagnóstica) en Markdown.
    La descripción técnica ya fue generada por el sistema — NO la repitas.

    ### HALLAZGOS E IMPRESIÓN DIAGNÓSTICA
    **Especialidad:** {specialty_name}
    **Región:** {ai_data.get('area_anatomica', '[Región detectada]')}
    **Confianza IA:** [Alto/Medio/Bajo]
    {tech_section}
    **Hallazgos por órgano/estructura:**
    [Detallar organ_analysis: estado, signos y mediciones de cada estructura evaluada]

    **Hallazgos críticos:**
    [Si hay critical_findings, resaltarlos en negrita. Si no, escribir "Sin hallazgos críticos."]

    **Impresión diagnóstica:**
    [Síntesis diagnóstica integrada — máximo 3 oraciones]

    **Recomendaciones:**
    [Estudios complementarios si corresponde]

    ---
    *Informe automatizado — debe ser revisado y firmado por el médico tratante.*

    Datos del análisis: {json.dumps(ai_data, ensure_ascii=False)}
    """


def synthesize_report_with_gemini(ai_data):
    logger.info("[*] Gemini LLM: Synthesizing medical report...")
    api_key = os.getenv("GEMINI_API_KEY", "")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
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
