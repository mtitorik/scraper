@echo off
setlocal enabledelayedexpansion

echo === Building Scraper for Windows ===
cd /d "%~dp0\.."

if exist .venv\Scripts\activate.bat (
    call .venv\Scripts\activate.bat
)

rem Clean previous builds
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

echo Running PyInstaller...
pyinstaller --clean -y packaging\scraper_windows.spec

cd dist
echo Creating zip archive...
powershell -Command "Compress-Archive -Path 'Scraper' -DestinationPath 'Scraper-Windows-x64.zip' -Force"

echo === Build Complete: dist\Scraper-Windows-x64.zip ===
pause
