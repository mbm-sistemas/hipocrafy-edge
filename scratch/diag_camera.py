import cv2

def list_cameras():
    print("--- Buscando dispositivos de captura ---")
    for i in range(5):
        cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
        if cap.isOpened():
            w = cap.get(cv2.CAP_PROP_FRAME_WIDTH)
            h = cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
            print(f"Indice {i}: DISPOSITIVO ENCONTRADO")
            print(f"  - Resolucion actual: {int(w)}x{int(h)}")
            
            # Probar resoluciones comunes para Mindray
            for res in [(800, 600), (1024, 768), (1280, 720)]:
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, res[0])
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, res[1])
                new_w = cap.get(cv2.CAP_PROP_FRAME_WIDTH)
                new_h = cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
                print(f"  - Intento {res[0]}x{res[1]} -> Resulto en: {int(new_w)}x{int(new_h)}")
            
            cap.release()
        else:
            print(f"Indice {i}: No disponible")

if __name__ == "__main__":
    list_cameras()
