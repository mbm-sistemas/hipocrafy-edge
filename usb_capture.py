import cv2
import httpx
import sys
import os
import time

# Fix Windows console encoding
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

GATEWAY_URL = "http://127.0.0.1:8080/api/capture"

def capture_and_send(patient_dni="00000000", cam_index=1):
    print(f"Buscando capturadora USB en el indice {cam_index}...")
    
    cap = cv2.VideoCapture(cam_index, cv2.CAP_DSHOW)
    if not cap.isOpened():
        print(f"No se pudo abrir la camara en el indice {cam_index}. Probando busqueda automatica...")
        for i in range(5):
            if i == 0: continue # Saltamos la webcam
            temp_cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
            if temp_cap.isOpened():
                print(f"Capturadora encontrada en el indice {i}")
                cap = temp_cap
                break
            temp_cap.release()

    if not cap:
        print("No se encontro ninguna capturadora USB conectada.")
        return

    # Dar tiempo a la cámara para que se estabilice
    time.sleep(2)

    ret, frame = cap.read()
    if not ret:
        print("Error al capturar la imagen.")
        cap.release()
        return

    # Guardar temporalmente
    temp_filename = "capture_temp.jpg"
    cv2.imwrite(temp_filename, frame)
    cap.release()
    
    print("Imagen capturada con exito.")

    # Enviar al Gateway local
    print(f"Enviando al Gateway para DNI: {patient_dni}...")
    try:
        with open(temp_filename, "rb") as f:
            files = {"image": ("capture.jpg", f, "image/jpeg")}
            data = {"patient_dni": patient_dni, "modality": "US"}
            
            response = httpx.post(GATEWAY_URL, data=data, files=files, timeout=30.0)
            
        if response.status_code == 200:
            result = response.json()
            print("Prueba exitosa!")
            print(f"ID Estudio: {result['study_id']}")
            print(f"Hallazgo IA: {result['findings']['finding']} ({result['findings']['confidence']*100:.1f}%)")
        else:
            print(f"El Gateway respondio con error {response.status_code}: {response.text}")
    except Exception as e:
        print(f"Error de conexion con el Gateway: {e}")
    finally:
        if os.path.exists(temp_filename):
            os.remove(temp_filename)

if __name__ == "__main__":
    dni = sys.argv[1] if len(sys.argv) > 1 else "12345678"
    # Si pasas un segundo numero, usa ese como indice de camara. Si no, prueba con el 1.
    cam_index = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    capture_and_send(dni, cam_index)
