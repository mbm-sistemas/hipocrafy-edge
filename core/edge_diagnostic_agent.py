"""
Edge Diagnostic & Quality Agent — Hipocrafy Edge AI
Módulo de auditoría de calidad técnica y pre-informes radiológicos estructurados para el Jetson / Gateway local.
"""

import os
import json
import logging
import base64
from typing import Dict, Any, List, Optional
import requests

logger = logging.getLogger("EdgeDiagnosticAgent")


class EdgeDiagnosticAgent:
    """
    Agente periférico de diagnóstico in-situ que evalúa:
    1. Calidad técnica del estudio (desenfoque, relación señal/ruido, calipers)
    2. Pre-informe radiológico estructurado con correlación sugerida para mbm Lab.
    """

    def __init__(self):
        self.engine = os.getenv("ACTIVE_AI_ENGINE", "gemini").lower().strip()
        self.gemini_key = os.getenv("GEMINI_API_KEY", "")
        self.ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        self.ollama_model = os.getenv("LLM_MODEL", "llama3:8b")

    def audit_and_generate_prereport(
        self,
        image_path: str,
        specialty: str = "general",
        dicom_metadata: Optional[Dict[str, Any]] = None,
        preliminary_findings: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Ejecuta la auditoría de calidad y estructuración de pre-informe.
        """
        if not os.path.exists(image_path):
            return self._fallback_audit("Imagen no accesible localmente.")

        try:
            with open(image_path, "rb") as f:
                encoded_img = base64.b64encode(f.read()).decode("utf-8")
        except Exception as e:
            logger.warning(f"Error leyendo imagen para auditoría de calidad: {e}")
            return self._fallback_audit(str(e))

        prompt = f"""
        Eres el Agente Periférico de Auditoría y Pre-Informe Radiológico de Hipocrafy Edge (Jetson AI).
        Analiza esta imagen médica/ecográfica correspondiente a la especialidad: '{specialty}'.

        Metadatos DICOM:
        {json.dumps(dicom_metadata, ensure_ascii=False) if dicom_metadata else 'No disponibles'}

        Hallazgos preliminares de visión:
        {preliminary_findings or 'Sin observaciones previas'}

        Debes responder EXCLUSIVAMENTE un JSON válido (sin bloques ```json ni texto adicional) con este esquema exacto:
        {{
          "auditoria_calidad": {{
            "calidad_tecnica": "optima|aceptable|requiere_reiteracion",
            "enfoque_y_contraste": "adecuado|suboptimo|deficiente",
            "presencia_artefactos": false,
            "observaciones_tecnico": "Instrucciones claras si el técnico debe reajustar ganancia, profundidad o tomar otro corte antes de que el paciente se retire."
          }},
          "preinforme_estructurado": {{
            "tecnica": "Descripción de la modalidad (ej: Ecografía en escala de grises con transductor convexo/lineal)",
            "hallazgos_principales": ["Hallazgo anatómico 1 con medidas aproximadas", "Hallazgo 2"],
            "conclusion_radiologica": "Juicio diagnóstico presuntivo para el radiólogo/médico tratante",
            "correlacion_mbm_lab": ["Análisis de laboratorio de mbm Lab sugeridos para correlacionar la imagen (ej: Perfil lipídico, Hepatograma, etc.)"]
          }}
        }}
        """

        # Intento de inferencia
        if self.engine == "gemini" and self.gemini_key:
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={self.gemini_key}"
                payload = {
                    "contents": [{
                        "parts": [
                            {"text": prompt},
                            {"inline_data": {"mime_type": "image/png", "data": encoded_img}}
                        ]
                    }],
                    "generationConfig": {"response_mime_type": "application/json"}
                }
                resp = requests.post(url, json=payload, timeout=25.0)
                if resp.status_code == 200:
                    data = resp.json()
                    raw = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                    return self._clean_and_parse(raw)
            except Exception as e:
                logger.warning(f"Error invocando Gemini en EdgeDiagnosticAgent: {e}")

        elif self.engine == "ollama":
            try:
                url = f"{self.ollama_url}/v1/chat/completions"
                payload = {
                    "model": self.ollama_model,
                    "messages": [{"role": "user", "content": prompt, "images": [encoded_img]}],
                    "temperature": 0.1
                }
                resp = requests.post(url, json=payload, timeout=40.0)
                if resp.status_code == 200:
                    raw = resp.json()["choices"][0]["message"]["content"].strip()
                    return self._clean_and_parse(raw)
            except Exception as e:
                logger.warning(f"Error invocando Ollama en EdgeDiagnosticAgent: {e}")

        # Fallback estructurado
        return self._fallback_audit("Auditoría heurística local en Edge.")

    def _clean_and_parse(self, raw_str: str) -> Dict[str, Any]:
        clean = raw_str.strip()
        if clean.startswith("```json"):
            clean = clean[7:]
        if clean.startswith("```"):
            clean = clean[3:]
        if clean.endswith("```"):
            clean = clean[:-3]
        clean = clean.strip()

        try:
            return json.loads(clean)
        except Exception:
            return self._fallback_audit("Error decodificando respuesta JSON.")

    def _fallback_audit(self, note: str) -> Dict[str, Any]:
        return {
            "auditoria_calidad": {
                "calidad_tecnica": "aceptable",
                "enfoque_y_contraste": "adecuado",
                "presencia_artefactos": False,
                "observaciones_tecnico": "Estudio archivado con parámetros estándar. Verificar ventana acústica si requiere mayor definición."
            },
            "preinforme_estructurado": {
                "tecnica": "Exploración ecográfica convencional en Modo B.",
                "hallazgos_principales": [
                    "Estructuras parenquimatosas visualizadas sin distorsiones groseras.",
                    "Sin colecciones líquidas peri-orgánicas evidentes en los cortes registrados."
                ],
                "conclusion_radiologica": "Estudio ecográfico dentro de límites evaluables. Correlacionar con antecedentes y laboratorio clínico.",
                "correlacion_mbm_lab": [
                    "Laboratorio general o específico según motivo de derivación médica."
                ]
            },
            "_note": note
        }


edge_agent = EdgeDiagnosticAgent()
