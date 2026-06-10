from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
import os
import glob
import datetime

app = FastAPI(title="Hipocrafy Gateway Local API")

RECEIVED_DIR = os.path.join(os.path.dirname(__file__), 'estudios_recibidos')
PROCESSED_DIR = os.path.join(os.path.dirname(__file__), 'estudios_procesados')
os.makedirs(RECEIVED_DIR, exist_ok=True)
os.makedirs(PROCESSED_DIR, exist_ok=True)

@app.get("/status")
def get_status():
    return {"status": "online", "message": "Hipocrafy Gateway is listening for DICOM data."}

@app.get("/studies")
def list_studies():
    """Returns a list of received DICOM files."""
    files = glob.glob(os.path.join(RECEIVED_DIR, "*.dcm"))
    return {"count": len(files), "studies": [os.path.basename(f) for f in files]}

@app.get("/studies/{filename}")
def get_study(filename: str):
    file_path = os.path.join(RECEIVED_DIR, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(file_path)

@app.get("/dashboard", response_class=HTMLResponse)
def technician_dashboard():
    """Dashboard local para el Técnico. Muestra subidas e interacciones con IA."""
    files = glob.glob(os.path.join(RECEIVED_DIR, "*.dcm"))
    files.sort(key=os.path.getmtime, reverse=True)
    
    # Construir log de subidas
    logs_html = ""
    for f in files[:10]:
        filename = os.path.basename(f)
        mtime = datetime.datetime.fromtimestamp(os.path.getmtime(f)).strftime('%Y-%m-%d %H:%M:%S')
        size = os.path.getsize(f) / 1024 # KB
        
        # Check if processed image exists
        uid_part = filename.split('_')[1].split('.')[0] if '_' in filename else filename
        processed = any(uid_part in p for p in os.listdir(PROCESSED_DIR))
        status_badge = '<span class="bg-green-100 text-green-800 text-xs font-semibold px-2.5 py-0.5 rounded">Procesado IA + Nube</span>' if processed else '<span class="bg-yellow-100 text-yellow-800 text-xs font-semibold px-2.5 py-0.5 rounded">Capturado (Pendiente IA)</span>'
        
        logs_html += f"""
        <tr class="bg-white border-b">
            <td class="px-6 py-4">{mtime}</td>
            <td class="px-6 py-4">{filename}</td>
            <td class="px-6 py-4">{size:.1f} KB</td>
            <td class="px-6 py-4">{status_badge}</td>
        </tr>
        """
        
    html_content = f"""
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Hipocrafy - Dashboard del Técnico (Edge)</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
        <style>body {{ font-family: 'Inter', sans-serif; background-color: #f3f4f6; }}</style>
    </head>
    <body class="p-8">
        <div class="max-w-6xl mx-auto">
            <div class="flex items-center justify-between mb-8">
                <div>
                    <h1 class="text-3xl font-bold text-gray-900">Hipocrafy Edge Gateway</h1>
                    <p class="text-gray-500 mt-1">Panel de Control Local del Técnico Capturador</p>
                </div>
                <div class="bg-blue-600 text-white px-4 py-2 rounded-lg font-medium shadow flex items-center gap-2">
                    <span class="relative flex h-3 w-3">
                      <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-white opacity-75"></span>
                      <span class="relative inline-flex rounded-full h-3 w-3 bg-white"></span>
                    </span>
                    Gateway Activo
                </div>
            </div>

            <div class="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
                <div class="p-6 border-b border-gray-100 flex justify-between items-center bg-gray-50">
                    <h2 class="text-lg font-semibold text-gray-800">Últimas Capturas (Estudios Recibidos)</h2>
                    <button onclick="window.location.reload()" class="text-sm text-blue-600 hover:text-blue-800 font-medium">Actualizar Lista</button>
                </div>
                <div class="overflow-x-auto">
                    <table class="w-full text-sm text-left text-gray-500">
                        <thead class="text-xs text-gray-700 uppercase bg-gray-50">
                            <tr>
                                <th scope="col" class="px-6 py-3">Fecha / Hora</th>
                                <th scope="col" class="px-6 py-3">Archivo DICOM</th>
                                <th scope="col" class="px-6 py-3">Tamaño</th>
                                <th scope="col" class="px-6 py-3">Estado del Flujo</th>
                            </tr>
                        </thead>
                        <tbody>
                            {logs_html if logs_html else '<tr><td colspan="4" class="px-6 py-8 text-center text-gray-400">No se han recibido estudios en esta sesión.</td></tr>'}
                        </tbody>
                    </table>
                </div>
            </div>
            
            <div class="mt-8 bg-blue-50 border border-blue-100 rounded-xl p-6">
                <h3 class="text-blue-800 font-semibold mb-2">Recordatorio para Captura</h3>
                <p class="text-blue-600 text-sm">Al iniciar un nuevo estudio en el ecógrafo, asegúrate de ingresar el <strong>DNI del paciente en el campo "Patient ID"</strong>. Esto es indispensable para que los estudios se vinculen correctamente en la nube.</p>
            </div>
        </div>
    </body>
    </html>
    """
    return html_content

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
