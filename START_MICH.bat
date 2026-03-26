@echo off
chcp 65001 >nul
title TUXPLAYER Backup System

python tuxplayer_backup_gui.py 2>nul
if %errorlevel% == 0 goto :end

python3 tuxplayer_backup_gui.py 2>nul
if %errorlevel% == 0 goto :end

echo.
echo ============================================================
echo  Python wurde nicht gefunden!
echo ============================================================
echo.
echo  Bitte installiere Python (kostenlos, 1 Minute):
echo.
echo  1. Gehe zu: https://www.python.org/downloads/
echo  2. Klicke auf den grossen gelben Download-Button
echo  3. Starte die Installation
echo  4. WICHTIG: Haken setzen bei "Add Python to PATH"
echo  5. Auf "Install Now" klicken
echo  6. Danach diese Datei nochmal doppelklicken
echo.
echo ============================================================
pause
:end
