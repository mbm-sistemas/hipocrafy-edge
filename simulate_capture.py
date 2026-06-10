import os
import random
import sys
import httpx

def run_simulation(dni=None, specialty=None, image_file=None):
    # Set directories
    base_dir = os.path.dirname(os.path.abspath(__file__))
    previews_dir = os.path.join(base_dir, "static", "previews")
    
    if not os.path.exists(previews_dir):
        print(f"❌ Error: La ruta {previews_dir} no existe.")
        return -1
        
    # Get all jpg files
    jpg_files = [f for f in os.listdir(previews_dir) if f.endswith('.jpg') and not f.startswith('CAP_')]
    if not jpg_files:
        jpg_files = [f for f in os.listdir(previews_dir) if f.endswith('.jpg')]
        
    if not jpg_files:
        print(f"❌ Error: No se encontraron imágenes en {previews_dir}")
        return -1
        
    # Choose image
    if image_file:
        chosen_image = image_file
        if not os.path.isabs(chosen_image):
            chosen_image = os.path.join(previews_dir, chosen_image)
    else:
        chosen_image = os.path.join(previews_dir, random.choice(jpg_files))
        
    if not os.path.exists(chosen_image):
        print(f"❌ Error: El archivo {chosen_image} no existe.")
        return -1
        
    # Setup parameters
    patient_dni = dni if dni else "30456789"
    active_specialty = specialty if specialty else "radiología general"
    
    print(f"\n==================================================")
    print(f"🚀 SIMULANDO ESTUDIO DESDE EL ECÓGRAFO")
    print(f"==================================================")
    print(f"📍 Imagen elegida:  {os.path.basename(chosen_image)}")
    print(f"👤 Paciente DNI:   {patient_dni}")
    print(f"🧠 Especialidad:   {active_specialty}")
    print(f"==================================================\n")
    
    # Upload image to local gateway endpoint
    url = "http://localhost:8080/api/capture"
    
    files = {
        "image": (os.path.basename(chosen_image), open(chosen_image, "rb"), "image/jpeg")
    }
    
    data = {
        "patient_dni": patient_dni,
        "modality": "US",
        "specialty": active_specialty,
        "clinical_context": "Estudio simulado de control ecográfico",
        "patient_age": "32",
        "patient_sex": "F"
    }
    
    print("[*] Enviando imagen al Gateway local (esto procesará con Gemini y sincronizará a la nube)...")
    try:
        with httpx.Client(timeout=120.0) as client:
            r = client.post(url, files=files, data=data)
            
        if r.status_code == 200:
            res_data = r.json()
            print("\n✅ ¡SIMULACIÓN EXITOSA!")
            print(f"📍 Study ID local: {res_data.get('study_id')}")
            
            findings = res_data.get("findings", {})
            print(f"🧠 Resultados IA:")
            print(f"   - Confianza: {findings.get('confidence', 'LOW')}")
            print(f"   - Estructuras: {', '.join(findings.get('structures', []))}")
            print(f"   - Hallazgos: {', '.join(findings.get('findings', []))}")
            print(f"\n📄 Informe:\n{res_data.get('report')}")
            print("-" * 50)
            print("\nYa puedes ver la actualización en:")
            print("  1. Dashboard local del Gateway (http://192.168.1.61:8080/)")
            print("  2. La Cabina de Mando (Command Center) de Hipocrafy en la nube")
            print("  3. El panel del médico en la nube")
            return 0
        else:
            print(f"\n❌ ERROR {r.status_code} del Gateway:")
            print(r.text)
            return -1
    except Exception as e:
        print(f"\n❌ Error de red / conexión: {e}")
        return -1

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Simulador de ecógrafo cargando imágenes locales")
    parser.add_argument("--dni", help="DNI del paciente para asociar")
    parser.add_argument("--specialty", help="Especialidad médica para el prompt de Gemini")
    parser.add_argument("--image", help="Nombre de archivo de imagen específico en static/previews")
    
    args = parser.parse_args()
    sys.exit(run_simulation(args.dni, args.specialty, args.image))
