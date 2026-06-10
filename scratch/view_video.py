import cv2

def view_video(cam_index=1):
    print(f"Abriendo vista previa en vivo (Indice {cam_index})...")
    print("Presiona 'q' para cerrar la ventana.")
    
    cap = cv2.VideoCapture(cam_index, cv2.CAP_DSHOW)
    
    # Intentamos forzar la resolucion tipica del Mindray
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 800)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 600)
    
    if not cap.isOpened():
        print("Error: No se pudo abrir la capturadora.")
        return

    while True:
        ret, frame = cap.read()
        if not ret:
            print("Error: No se reciben frames.")
            break
            
        cv2.imshow('Prueba de Video - Hipocrafy', frame)
        
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
            
    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    view_video(1)
