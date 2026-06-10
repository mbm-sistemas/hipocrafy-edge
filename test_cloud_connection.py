import os
import httpx
from dotenv import load_dotenv
import sys

# Forzar la ruta al directorio del script
os.chdir(os.path.dirname(os.path.abspath(__file__)))

load_dotenv()

TOKEN = os.getenv("GATEWAY_API_TOKEN")
# Usamos la URL de QAS por defecto si no esta en el env
CLOUD_URL = os.getenv("HIPOCRAFY_CLOUD_URL", "https://qas.hipocrafy-api.mbmsistemas.com.ar/api/edge-gateway")

print(f"\n" + "="*50)
print(f"   VERIFICADOR DE CONEXION HIPOCRAFY CLOUD")
print(f"   Ambiente: QAS / Produccion")
print("="*50)

def test():
    if not TOKEN or TOKEN == "tu_token_aqui" or len(TOKEN) < 10:
        print("\n❌ ERROR: Token no configurado.")
        print("   Por favor, crea un Gateway en el panel de Admin de la Nube,")
        print("   copia el Token y pegalo en el archivo .env")
        return

    print(f"\n[1/2] Probando endpoint: {CLOUD_URL}/config")
    print(f"      Token: {TOKEN[:8]}...{TOKEN[-8:]}")

    headers = {
        "X-Gateway-Token": TOKEN,
        "Authorization": f"Bearer {TOKEN}"
    }
    
    try:
        with httpx.Client(timeout=15.0) as client:
            response = client.get(f"{CLOUD_URL}/config", headers=headers)
        
        if response.status_code == 200:
            data = response.json()
            print("\n✅ ¡CONEXION EXITOSA!")
            print(f"\n--- INFORMACION DEL EQUIPO ---")
            print(f"📍 Nombre en Nube: {data.get('gateway_name')}")
            print(f"🏥 Organizacion:    {data.get('clinic_name')}")
            
            subs = [s.get('service_type') for s in data.get('subscriptions', [])]
            print(f"📦 Servicios:      {', '.join(subs) if subs else 'Ninguno (Solo diagnostico base)'}")
            print("-" * 30)
            print("\nYa puedes cerrar este script y lanzar 'start_gateway.bat'")
            
        elif response.status_code == 401:
            print("\n❌ ERROR 401: Autorizacion fallida.")
            print("   El Token es incorrecto o fue revocado en la nube.")
        elif response.status_code == 404:
            print("\n❌ ERROR 404: Endpoint no encontrado.")
            print(f"   Verifica que la URL {CLOUD_URL} sea la correcta.")
        else:
            print(f"\n❌ ERROR {response.status_code}: Respuesta inesperada del servidor.")
            print(response.text)
            
    except httpx.ConnectError:
        print("\n❌ ERROR DE RED: No se pudo contactar al servidor.")
        print("   Verifica tu conexion a internet o que la URL sea correcta.")
    except Exception as e:
        print(f"\n❌ ERROR INESPERADO: {str(e)}")

if __name__ == "__main__":
    test()
    print("\n" + "="*50)
    input("Presiona Enter para salir...")
