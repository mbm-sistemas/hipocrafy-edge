# Guía de Configuración DICOM: Mindray Z50 -> Hipocrafy AI Edge

Esta guía detalla los pasos para conectar tu ecógrafo Mindray Z50 al gateway de inteligencia artificial.

## 1. Datos del Servidor (Hipocrafy Edge)
Asegúrate de tener estos datos a mano antes de empezar:
- **IP del Gateway**: [Obtener la IP de la Jetson/PC donde corre el gateway]
- **AE Title**: `HIPOCRAFY_IA`
- **Puerto**: `11112`

## 2. Configuración en el Mindray Z50

1.  **Acceder a Ajustes**: Presiona el botón **<Setup>** en el panel de control del ecógrafo.
2.  **Red (Network)**: Ve a la pestaña **Network Preset** (o Ajustes de Red).
3.  **Local Host**:
    *   Verifica que el ecógrafo tenga una IP en el mismo rango que el Gateway.
    *   Asigna un **AE Title** local (ej: `MINDRAY_Z50`).
4.  **DICOM Preset**:
    *   Ve a la sección **DICOM Preset** o **DICOM Service**.
    *   Selecciona el servicio **Storage** (Almacenamiento) y haz clic en **Add** (Añadir).
5.  **Configurar el Servicio**:
    *   **Service Name**: `Hipocrafy_IA`
    *   **AE Title**: `HIPOCRAFY_IA` (Debe ser exacto)
    *   **Port**: `11112`
    *   **IP Address**: [La IP del Gateway]
6.  **Verificación**:
    *   Haz clic en el botón **Verify** o **Ping**.
    *   Debería aparecer el mensaje: **"Verification Succeeded"**.
7.  **Guardar**: Haz clic en **OK** o **Save** para confirmar.

## 3. Protocolo de Captura (MUY IMPORTANTE)

Para que la IA pueda procesar el estudio y vincularlo al paciente en la nube:

- **Patient ID**: Debe ser obligatoriamente el **DNI** del paciente (sin puntos ni espacios).
- **Envío**: Al finalizar el estudio, selecciona las imágenes y elige la opción **Send to -> Hipocrafy_IA**.

---
*Nota: Si el test de verificación falla, asegúrate de que no haya un firewall bloqueando el puerto 11112 en la computadora del gateway.*
