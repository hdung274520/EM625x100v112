@echo off
rem Build "dist\Nplay AIM.exe" (one file, no console window).
rem Needs Python 3.10+ from python.org (with the "py" launcher).
cd /d "%~dp0"
py -m pip install -r requirements.txt pyinstaller || exit /b 1
py -m unittest discover -s tests || exit /b 1
py -m PyInstaller --noconfirm --onefile --windowed --name "Nplay AIM" --icon icon.ico --version-file version_info.txt ^
  --paths ..\linux-native ^
  --add-data "..\linux-native\nplayaim\data;nplayaim\data" ^
  run.pyw || exit /b 1
rem Installer (optional): Inno Setup 6 from https://jrsoftware.org/isdl.php
set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" set "ISCC=%LocalAppData%\Programs\Inno Setup 6\ISCC.exe"
if exist "%ISCC%" (
  "%ISCC%" installer.iss || exit /b 1
) else (
  echo Chua cai Inno Setup 6 - bo qua buoc tao installer.
)
echo.
echo Xong: %~dp0dist\
