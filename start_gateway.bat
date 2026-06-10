@echo off
echo ==========================================
echo   Hipocrafy Edge Gateway - Auto Launcher
echo ==========================================
echo.

echo cd /d "%~dp0"

echo [INFO] Iniciando servicios DICOM (Orthanc)...
echo docker-compose up -d

echo if not exist venv (
    echo [INFO] Creando entorno virtual Python...
     python -m venv venv
echo )

echo [INFO] Activando entorno...
echo call venv\Scripts\activate

echo [INFO] Verificando dependencias...
echo pip install -q fastapi uvicorn httpx pydicom python-dotenv jinja2 requests pillow

echo.
echo [OK] El servidor esta listo.
echo [INFO] Lanzando Dashboard Local en http://localhost:8080
echo.

echo uvicorn main:app --reload --port 8080

echo pause
@echo off
echo ==========================================
echo   Hipocrafy Edge Gateway - Auto Launcher
echo ==========================================
echo.

cd /d "%~dp0"

echo [INFO] Iniciando servicios DICOM (Orthanc)...
docker-compose up -d

if not exist venv (
    echo [INFO] Creando entorno virtual Python...
    python -m venv venv
)

echo [INFO] Activando entorno...
call venv\Scripts\activate

echo [INFO] Verificando dependencias...
pip install -q fastapi uvicorn httpx pydicom python-dotenv jinja2 requests pillow

echo [INFO] Iniciando Vision Extractor (puerto 5001)...
start "Vision Extractor" cmd /c "venv\Scripts\python vision_extractor.py"

echo.
echo [OK] Servidores listos:
echo   - Vision Extractor: http://localhost:5001
echo   - Dashboard Edge:   http://localhost:8080
echo.

timeout /t 3

start http://localhost:8080

echo [INFO] Lanzando Dashboard...
uvicorn main:app --reload --port 8080

pause