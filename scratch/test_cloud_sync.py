import httpx
import json
import asyncio
import os
import sys
from datetime import datetime
from dotenv import load_dotenv

# Configuración
load_dotenv()
GATEWAY_URL = "http://localhost:8080"
CLOUD_URL = os.getenv("HIPOCRAFY_CLOUD_URL", "https://qas.hipocrafy-api.mbmsistemas.com.ar/api/edge-gateway")
API_TOKEN = os.getenv("GATEWAY_API_TOKEN")

async def test_cloud_sync():
    print("=" * 60)
    print("🚀 HIPOCRAFY EDGE - TEST DE SINCRONIZACIÓN NUBE")
    print("=" * 60)

    if not API_TOKEN:
        print("❌ ERROR: No se encontró GATEWAY_API_TOKEN en el archivo .env")
        print("   Por favor, configurá el token antes de correr este test.")
        return

    # 1. Verificar Salud del Gateway
    print(f"\n1. Verificando Gateway Local ({GATEWAY_URL})...")
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(f"{GATEWAY_URL}/health", timeout=5.0)
            if resp.status_code == 200:
                data = resp.json()
                print(f"   ✅ Gateway ONLINE. Cloud Status: {data.get('cloud_status')}")
            else:
                print(f"   ⚠️  Gateway respondió con status {resp.status_code}. ¿Está encendido?")
                return
        except Exception as e:
            print(f"   ❌ No se pudo conectar al Gateway: {e}")
            print("      Asegurate de correr: python main.py")
            return

    # 2. Simular un hallazgo de IA
    fake_study = {
        "patient_document": "TEST-123456",
        "study_date": datetime.now().isoformat(),
        "modality": "US",
        "ai_findings": {
            "finding": "Normal",
            "confidence": 0.95,
            "anomalies": [],
            "notes": "Sincronización de prueba generada por script de diagnóstico."
        }
    }

    # 3. Probar Conexión Directa a la Nube (Bypass Gateway)
    print(f"\n2. Probando conexión directa a la Nube ({CLOUD_URL})...")
    headers = {"Authorization": f"Bearer {API_TOKEN}", "Accept": "application/json"}
    
    async with httpx.AsyncClient() as client:
        try:
            # Intentar obtener configuración (Ping de auth)
            resp = await client.get(f"{CLOUD_URL}/config", headers=headers)
            if resp.status_code == 200:
                print("   ✅ Autenticación con la Nube EXITOSA.")
                clinic_data = resp.json()
                print(f"      Clínica: {clinic_data.get('clinic_name')}")
            else:
                print(f"   ❌ Error de Autenticación: {resp.status_code}")
                print(f"      Detalle: {resp.text}")
                return
        except Exception as e:
            print(f"   ❌ Error de conexión con la Nube: {e}")
            return

    # 4. Simular envío de estudio a través de la API del Gateway
    # Nota: El gateway usa X-Gateway-Token internamente si se llama a sus endpoints de sync
    print("\n3. Enviando estudio de prueba a la Nube...")
    try:
        # Usamos el endpoint del backend directamente para validar el token
        resp = await client.post(f"{CLOUD_URL}/studies", json=fake_study, headers=headers)
        if resp.status_code in [200, 201]:
            print("   ✅ ESTUDIO SINCRONIZADO CORRECTAMENTE.")
            print(f"      Study ID en Nube: {resp.json().get('study_id')}")
        else:
            print(f"   ❌ Error al sincronizar estudio: {resp.status_code}")
            print(f"      {resp.text}")
    except Exception as e:
        print(f"   ❌ Error durante el envío: {e}")

    print("\n" + "=" * 60)
    print("🏁 TEST FINALIZADO")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(test_cloud_sync())
