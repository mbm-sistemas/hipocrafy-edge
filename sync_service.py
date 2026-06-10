import os
import requests
import logging
import json
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration
MBM_LAB_API_BASE = os.getenv("MBM_LAB_API_BASE", "http://127.0.0.1:8000/api")
API_TOKEN = os.getenv("MBM_LAB_API_TOKEN", "LOCAL_HUB_SECURE_TOKEN_001")
TIMEOUT = 10 

logger = logging.getLogger("HipocrafySync")

def get_auth_headers():
    headers = {
        "Authorization": f"Bearer {API_TOKEN}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    return headers

def get_api_url(endpoint):
    """Retorna la URL dinámica. Prioriza Localhost si está configurado."""
    return f"{MBM_LAB_API_BASE.rstrip('/')}/{endpoint.lstrip('/')}"

def get_available_pathologies():
    """Obtiene el maestro de patologías del backend (Admin)."""
    try:
        url = get_api_url("admin/pathologies")
        # verify=False solo para HTTPS con IP directa o certificados auto-firmados
        verify = not ("127.0.0.1" in url or "localhost" in url)
        resp = requests.get(url, headers=get_auth_headers(), timeout=TIMEOUT, verify=verify)
        if resp.status_code == 200:
            return resp.json().get('data', resp.json())
        return []
    except Exception as e:
        logger.error(f"Error fetching pathologies: {e}")
        return []

def get_patient_clinical_context(dni):
    """Obtiene el historial clínico relevante (SOS, laboratorios, patologías) del paciente."""
    if not dni or dni == "UNKNOWN": return None
    
    try:
        url = get_api_url(f"admin/users/find-by-dni/{dni}")
        verify = not ("127.0.0.1" in url or "localhost" in url)
        resp = requests.get(url, headers=get_auth_headers(), timeout=TIMEOUT, verify=verify)
        
        if resp.status_code == 200:
            user_data = resp.json()
            pathologies = ", ".join([p['name'] for p in user_data.get('pathologies', [])])
            history = user_data.get('medical_history', [])
            recent_events = " | ".join([f"{h['type']}: {h['notes']}" for h in history[-3:]]) # Últimos 3 eventos
            
            context = f"Patologías previas: {pathologies}. Antecedentes recientes: {recent_events}."
            return context
        return None
    except Exception as e:
        logger.error(f"Error fetching clinical context: {e}")
        return None

def sync_patient_pathologies(dni, ai_findings):
    """Vincula los hallazgos de la IA con las patologías del paciente."""
    if not ai_findings or not dni or dni == "UNKNOWN": 
        logger.warning(f"[!] Sync Pathologies saltado: DNI inválido o vacío ({dni})")
        return
    
    logger.info(f"[*] Sincronizando hallazgos para DNI {dni}...")
    
    master_pathologies = get_available_pathologies()
    if not master_pathologies: return
    
    to_sync = []
    for finding in ai_findings:
        finding_clean = str(finding).lower().strip()
        for p in master_pathologies:
            p_name = str(p.get('name', '')).lower()
            p_code = str(p.get('code', '')).lower()
            if finding_clean in p_name or finding_clean == p_code:
                if p['id'] not in to_sync:
                    to_sync.append(p['id'])
                    logger.info(f"[+] Hallazgo '{finding}' mapeado a ID: {p['id']}")

    if not to_sync: return

    try:
        url = get_api_url("patient/pathologies") 
        payload = {"pathology_ids": to_sync, "dni_fallback": dni}
        verify = not ("127.0.0.1" in url or "localhost" in url)
        requests.post(url, json=payload, headers=get_auth_headers(), timeout=TIMEOUT, verify=verify)
    except Exception as e:
        logger.error(f"Error en sync_patient_pathologies: {e}")

def upload_ai_result(study_uid, report, ai_data):
    """Sube el informe final de la IA al backend (Admin)."""
    try:
        url = get_api_url(f"admin/studies/{study_uid}/analysis")
        payload = {
            "report": report,
            "ai_metadata": ai_data,
            "status": "COMPLETED"
        }
        verify = not ("127.0.0.1" in url or "localhost" in url)
        resp = requests.post(url, json=payload, headers=get_auth_headers(), timeout=TIMEOUT, verify=verify)
        return resp.status_code in [200, 201]
    except Exception as e:
        logger.error(f"Error en upload_ai_result: {e}")
        return False

def sync_dicom_to_mbm_lab(dataset):
    """Registra al paciente y el estudio inicial (Metadatos Admin)."""
    # Usar el ID del paciente como DNI, siguiendo las instrucciones
    dni = str(getattr(dataset, 'PatientID', '')).strip()
    full_name = str(getattr(dataset, 'PatientName', '')).strip()
    study_uid = str(dataset.StudyInstanceUID).strip()
    
    if not dni or dni == "UNKNOWN":
        logger.warning(f"[!] Sync Inicial saltado: DNI inválido ({dni})")
        return False

    logger.info(f"[*] Verificando Usuario en MBM Lab: {dni}")

    try:
        url_u = get_api_url(f"admin/users?dni={dni}")
        verify = not ("127.0.0.1" in url_u or "localhost" in url_u)
        resp_u = requests.get(url_u, headers=get_auth_headers(), timeout=TIMEOUT, verify=verify)
        
        users = resp_u.json().get('data', []) if resp_u.status_code == 200 else []
        patient_id = None
        
        if users:
            patient_id = users[0]['id']
        else:
            logger.info(f"[!] Creando nuevo usuario paciente {dni}...")
            create_resp = requests.post(get_api_url("admin/users"), 
                                      json={"dni": dni, "name": full_name, "role": "patient"}, 
                                      headers=get_auth_headers(), timeout=TIMEOUT, verify=verify)
            if create_resp.status_code == 201:
                patient_id = create_resp.json().get('id')
            else:
                return False

        study_payload = {
            "user_id": patient_id,
            "study_uid": study_uid,
            "modality": getattr(dataset, 'Modality', 'US')
        }
        requests.post(get_api_url("admin/studies"), json=study_payload, headers=get_auth_headers(), timeout=TIMEOUT, verify=verify)
        return True
    except Exception as e:
        logger.error(f"Sync Error: {e}")
        return False
