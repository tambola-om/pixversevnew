@echo off
chcp 65001 >nul
title Proxy CORS - Realisateur IA
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo Python est introuvable. Installez-le depuis https://www.python.org puis relancez ce fichier.
    pause
    exit /b 1
)

if not exist "proxy_ollama.py" (
    echo Le fichier proxy_ollama.py doit etre dans le meme dossier que ce fichier .bat.
    pause
    exit /b 1
)

echo Preparation des certificats (une seule fois)...
python -m pip install --quiet --disable-pip-version-check truststore >nul 2>nul
python -c "import truststore" >nul 2>nul
if errorlevel 1 (
    echo truststore indisponible : demarrage en mode --insecure.
    python proxy_ollama.py --insecure
) else (
    python proxy_ollama.py
)

echo.
echo Le proxy s'est arrete.
pause
