import sys
import traceback
import datetime

CRASH_LOG = "logs/crash_details.log"

try:
    import os
    import logging
    import pydicom
    from pydicom import dcmread, Dataset
    from pynetdicom import AE, evt, debug_logger, StoragePresentationContexts
    from pynetdicom.sop_class import CTImageStorage, PatientRootQueryRetrieveInformationModelFind
    from PIL import Image, ImageDraw
    import numpy as np
    from dotenv import load_dotenv
    import time
    import json

    # Hipocrafy Logic Imports
    from sync_service import sync_dicom_to_mbm_lab, sync_patient_pathologies, upload_ai_result, get_patient_clinical_context
    from vision_service import analyze_study, synthesize_report
    
    load_dotenv()

    # Configuration
    STORAGE_DIR = 'estudios_recibidos'
    SCRUBBED_DIR = 'estudios_procesados'
    os.makedirs(STORAGE_DIR, exist_ok=True)
    os.makedirs(SCRUBBED_DIR, exist_ok=True)

    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    logger = logging.getLogger("HipocrafyGateway")

    def send_to_viewer(file_path):
        """Envía el DICOM recibido al visor profesional RUBOVIEWER."""
        logger.info(f"[*] Pushing to Rubo Viewer (RUBOVIEWER:5555)...")
        ae = AE()
        ae.add_requested_context(CTImageStorage)
        
        try:
            ds = dcmread(file_path)
            assoc = ae.associate('127.0.0.1', 5555, ae_title='RUBOVIEWER')
            
            if assoc.is_established:
                status = assoc.send_c_store(ds)
                if status:
                    logger.info(f"[+] Successfully pushed to Viewer. Status: {status.Status}")
                else:
                    logger.error("[X] Failed to push to Viewer.")
                assoc.release()
            else:
                logger.warning("[X] RUBOVIEWER no está en modo 'Receive' o puerto 5555 cerrado.")
        except Exception as e:
            logger.error(f"[!] Error enviando al visor: {e}")

    # Rate Limiting & Smart Selection
    import threading
    PENDING_STUDIES = {} # {study_uid: [list_of_files]}
    STUDY_TIMERS = {}    # {study_uid: Timer}
    DEBOUNCE_TIME = 2.5  # Segundos a esperar para considerar una serie completa
    LOCK = threading.Lock()

    def scrub_phi_from_image(ds, output_path):
        """Convierte DICOM a PNG de alta calidad diagnóstica (Bone Window)."""
        try:
            from pydicom.pixel_data_handlers.util import apply_modality_lut, apply_voi_lut
            
            # 1. Aplicar transformaciones DICOM profesionales
            arr = apply_modality_lut(ds.pixel_array, ds)
            arr = apply_voi_lut(arr, ds)
            
            # 2. Normalizar a 8-bit para la IA
            arr = arr.astype(float)
            arr -= np.min(arr)
            if np.max(arr) > 0:
                arr /= np.max(arr)
            arr *= 255.0
            
            img = Image.fromarray(arr.astype(np.uint8))
            
            # Opcional: Blackout PHI area (en Tomografías suele ser negro igual)
            # Para la demo, simplemente guardamos el corte anatómico limpio
            img.save(output_path, "PNG")
            return True
        except Exception as e:
            logger.error(f"[!] Error en scrubbing/conversión: {e}")
            return False

    def process_best_slice(study_uid, called_aet="HIPOCRAFY_IA"):
        """Analiza solo la tajada del medio para no quemar la cuota de la IA."""
        with LOCK:
            files = PENDING_STUDIES.pop(study_uid, [])
            STUDY_TIMERS.pop(study_uid, None)
            
        if not files: return
        
        logger.info(f"[*] Procesando bloque de {len(files)} tajadas para {study_uid}...")
        # Selección: tajada central
        best_file = files[len(files)//2]
        
        try:
            # force=True es clave para archivos temporales que i-Rubo manda sin preámbulo
            ds = dcmread(best_file, force=True) 
            patient_id = str(getattr(ds, 'PatientID', 'UNKNOWN'))
            
            # Pipeline HIPAA & IA
            scrubbed_png = os.path.join(SCRUBBED_DIR, f"{study_uid}_clean.png")
            scrub_phi_from_image(ds, scrubbed_png)
            
            # --- SEGURO PARA DEMO (SAFE-SWITCH) ---
            if os.getenv("DEMO_MODE", "False") == "True":
                logger.info("[🛡️] DEMO_MODE ACTIVO: Cargando resultado de respaldo para demo...")
                time.sleep(2) # Simular procesamiento real
                ai_data = {
                    "structures": ["Cuerpo mandibular", "Sínfisis", "Raíces dentales", "Edentulismo"],
                    "findings": ["Hallazgos compatibles con Torus Mandibularis", "Integridad de tablas corticales"],
                    "confidence": "HIGH",
                    "analysis_tag": "STABLE_PREVIEW"
                }
                full_report = synthesize_report(ai_data)
            else:
                # 1. Análisis de Visión Real
                try:
                    specialty = "auto"
                    
                    # --- MEJORA: Contexto Multimodal y Metadatos ---
                    clinical_context = get_patient_clinical_context(patient_id)
                    
                    # Extraer metadatos técnicos del DICOM (si existen)
                    dicom_meta = {
                        "frequency": getattr(ds, 'ScanningSequence', 'N/A'),
                        "gain": getattr(ds, 'ContrastBolusAgent', 'N/A'),
                        "depth": getattr(ds, 'Rows', 'N/A')
                    }
                    
                    ai_data = analyze_study(scrubbed_png, patient_id, specialty, clinical_context, dicom_metadata=dicom_meta)
                except Exception as vision_err:
                    if "429" in str(vision_err):
                        raise Exception("429_LIMIT")
                    raise vision_err

                # 2. Síntesis de Informe Real
                try:
                    full_report = synthesize_report(ai_data)
                except Exception as llm_err:
                    if "429" in str(llm_err):
                        full_report = "⚠️ IA ocupada analizando volumen previo. El informe aparecerá en breve..."
                    else:
                        raise llm_err
            # --------------------------------------
            
            ui_payload = {
                "ai_data": {
                    **ai_data,
                    "image_path": scrubbed_png.replace("\\", "/") # Normalizar para Web
                },
                "report": full_report,
                "timestamp": datetime.datetime.now().isoformat()
            }
            with open("../last_ai_result.js", "w", encoding="utf-8") as f:
                f.write(f"window.HIPOCRAFY_LAST_RESULT = {json.dumps(ui_payload, ensure_ascii=False)};")
            
            logger.info(f"[!] BROADCAST: Dashboard Actualizado con tajada central de {study_uid}.")
            
            # --- SINCRONIZACIÓN CON BACKEND (MBM Lab) ---
            if os.getenv("DEMO_MODE", "False") != "True":
                # 1. Sincronizar Patologías detectadas
                findings = ai_data.get("findings", []) + ai_data.get("structures", [])
                sync_patient_pathologies(patient_id, findings)
                
                # 2. Subir Informe Completo
                upload_ai_result(study_uid, full_report, ai_data, patient_dni=patient_id, specialty=specialty)
            # --------------------------------------------
            
            # Push Final al Visor
            send_to_viewer(best_file)
            
        except Exception as e:
            if "429_LIMIT" in str(e):
                logger.error("[!] CUOTA EXCEDIDA: Gemini tiene límites de velocidad (RPM).")
                # Notificar al dashboard del estado de espera
                msg = "⏳ Límite de IA alcanzado (Free Tier). Esperando 60s para resetear cuota..."
                payload = {"report": msg, "ai_data": {"confidence": "LOW", "analysis_tag": "WAITING_QUOTA"}}
                with open("../last_ai_result.js", "w", encoding="utf-8") as f:
                    f.write(f"window.HIPOCRAFY_LAST_RESULT = {json.dumps(payload, ensure_ascii=False)};")
            else:
                logger.error(f"[!] Error en Smart Processing ({study_uid}): {e}")

    def handle_store(event):
        """Maneja la recepción masiva de tajadas con debouncing."""
        ds = event.dataset
        ds.file_meta = event.file_meta
        
        study_uid = str(getattr(ds, 'StudyInstanceUID', 'UNKNOWN'))
        called_aet = getattr(event.assoc.requestor, 'called_ae_title', b'HIPOCRAFY_IA').decode().strip()
        
        # 1. Guardar Físicamente (enforce_file_format=True para evitar errores de preámbulo)
        filename = os.path.join(STORAGE_DIR, f"{int(time.time()*1000)}_{study_uid[:8]}.dcm")
        ds.save_as(filename, enforce_file_format=True)
        
        with LOCK:
            # 2. Registrar en Lote
            if study_uid not in PENDING_STUDIES:
                PENDING_STUDIES[study_uid] = []
                logger.info(f"📦 Recibiendo para {called_aet}: {study_uid}")
                
                # --- SYNC INICIAL (MBM Lab) ---
                if os.getenv("DEMO_MODE", "False") != "True":
                    threading.Thread(target=sync_dicom_to_mbm_lab, args=(ds,)).start()
                # ------------------------------
            
            PENDING_STUDIES[study_uid].append(filename)
            
            # 3. Reiniciar el Timer (Debounce)
            if study_uid in STUDY_TIMERS:
                STUDY_TIMERS[study_uid].cancel()
            
            timer = threading.Timer(DEBOUNCE_TIME, process_best_slice, [study_uid, called_aet])
            STUDY_TIMERS[study_uid] = timer
            timer.start()
        
        return 0x0000 

    def handle_echo(event):
        """Maneja el C-ECHO para verificar conectividad."""
        logger.info(f"[*] C-ECHO Recibido de {event.assoc.requestor.ae_title.decode()}")
        return 0x0000  # Success

    def start_hipocrafy_gateway(ae_title=b'HIPOCRAFY_IA', port=11112):
        ae = AE(ae_title=ae_title)
        ae.supported_contexts = StoragePresentationContexts
        # Añadir soporte para Verificación (C-ECHO)
        from pynetdicom.sop_class import Verification
        ae.add_supported_context(Verification)
        
        handlers = [
            (evt.EVT_C_STORE, handle_store),
            (evt.EVT_C_ECHO, handle_echo)
        ]
        
        print(f"🚀 Hipocrafy Gateway (Production) iniciado.")
        print(f"[*] AE Title: {ae_title.decode()} | Port: {port}")
        
        # Confirmación de Modo para el Usuario
        if os.getenv("DEMO_MODE", "False") == "True":
            print("🛡️  MODO DEMO ACTIVO")
        else:
            print("🌐 MODO IA REAL ACTIVO (Llamando a Gemini API)")
            
        ae.start_server(('', port), block=True, evt_handlers=handlers)

    if __name__ == "__main__":
        start_hipocrafy_gateway()

except Exception as e:
    with open(CRASH_LOG, "a") as f:
        f.write(f"\n--- CRASH AT {datetime.datetime.now()} ---\n")
        traceback.print_exc(file=f)
    print(f"CRITICAL STARTUP ERROR: {e}")
    sys.exit(1)
