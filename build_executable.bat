@echo off
echo Building WetlabDB executable...
echo.

REM Convert PNG to ICO using Python and Pillow
echo Converting icon to ICO format...
python -c "from PIL import Image; img = Image.open('wetlabDB_icon.png'); img.save('wetlabDB_icon.ico')"

REM Update spec file to use ICO file
echo Updating spec file to use ICO...
python -c "content = open('wetlabDB.spec', 'r').read(); content = content.replace(\"icon='wetlabDB_icon.png'\", \"icon='wetlabDB_icon.ico'\"); open('wetlabDB.spec', 'w').write(content)"

echo Building executable...
if exist "dist\WetlabDB.exe" (
    echo Closing existing WetlabDB.exe if it is running...
    taskkill /IM WetlabDB.exe /F >nul 2>nul
    del /F /Q "dist\WetlabDB.exe" >nul 2>nul
    if exist "dist\WetlabDB.exe" (
        echo.
        echo Build failed: dist\WetlabDB.exe is locked or cannot be removed.
        echo Close WetlabDB, pause Synology Drive sync for this folder, or delete the EXE manually, then rerun this script.
        echo.
        pause
        exit /b 1
    )
)
python -m PyInstaller --clean wetlabDB.spec
if errorlevel 1 (
    echo.
    echo Build failed. If the error mentions "No module named PyInstaller",
    echo install it into the same Python environment first:
    echo     pip install pyinstaller
    echo.
    pause
    exit /b 1
)

echo.
echo Build complete! The executable is in the dist folder.
echo.
pause 