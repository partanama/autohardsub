@echo off
setlocal EnableDelayedExpansion
title Installer AutoHardsub - Setup Portabel

set "BASE_DIR=%~dp0"
if /i "%BASE_DIR:~-12%"=="AutoHardsub\" (
    set "INSTALL_DIR=%BASE_DIR:~0,-1%"
) else (
    set "INSTALL_DIR=%BASE_DIR%AutoHardsub"
)

mkdir "%INSTALL_DIR%" 2>nul
cd /d "%INSTALL_DIR%"

echo ========================================================
echo   AUTOHARDSUB PORTABLE INSTALLER
echo   Build Version : "Jemboed Kecelup Santen"
echo ========================================================
echo.
echo Folder instalasi: "%INSTALL_DIR%"
echo Pastikan koneksi internet aktif. Proses ini hanya sekali.
echo.

:: 1. Siapkan Python 3.11.9 Embeddable + pip
if exist "runtime_python\python.exe" (
    echo [1/4] Runtime Python sudah terpasang, melewati...
    goto STEP2
)

echo [1/4] Mengunduh runtime Python portabel...
mkdir "runtime_python" 2>nul
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ProgressPreference = 'SilentlyContinue'; Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.11.9/python-3.11.9-embed-amd64.zip' -OutFile 'python_embed.zip'; Expand-Archive -Path 'python_embed.zip' -DestinationPath 'runtime_python' -Force; Remove-Item 'python_embed.zip' -Force; $pth = 'runtime_python\python311._pth'; (Get-Content $pth) -replace '#import site', 'import site' | Set-Content $pth; Add-Content $pth '..'; Invoke-WebRequest -Uri 'https://bootstrap.pypa.io/get-pip.py' -OutFile 'runtime_python\get-pip.py'"

echo       Memasang pip...
"runtime_python\python.exe" "runtime_python\get-pip.py" --no-warn-script-location --quiet
del "runtime_python\get-pip.py" 2>nul

:STEP2
:: 2. Unduh Kode Aplikasi & Install Semua Library
echo [2/4] Mengunduh kode aplikasi dari GitHub...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ProgressPreference = 'SilentlyContinue'; Invoke-WebRequest -Uri 'https://github.com/partanama/autohardsub/archive/refs/heads/main.zip' -OutFile 'src_temp.zip'; Expand-Archive -Path 'src_temp.zip' -DestinationPath '_src_extract' -Force; Copy-Item -Path '_src_extract\autohardsub-main\*' -Destination '.' -Recurse -Force; Remove-Item 'src_temp.zip', '_src_extract' -Recurse -Force"

echo       Memasang PySide6 dan dependensi (mohon tunggu)...
"runtime_python\python.exe" -m pip install PySide6 --no-warn-script-location --quiet
if exist "requirements.txt" (
    "runtime_python\python.exe" -m pip install -r requirements.txt --no-warn-script-location --quiet
)

:: 3. Unduh Binary FFmpeg & Whisper dari GitHub Releases
if exist "assets\bin\ffmpeg.exe" (
    echo [3/4] Paket binary sudah ada, melewati...
    goto STEP4
)

echo [3/4] Mengunduh paket FFmpeg dan Whisper GPU (~85 MB)...
mkdir "assets\bin" 2>nul
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ProgressPreference = 'SilentlyContinue'; Invoke-WebRequest -Uri 'https://github.com/partanama/autohardsub/releases/latest/download/bin_bundle.zip' -OutFile 'bin_temp.zip'; Expand-Archive -Path 'bin_temp.zip' -DestinationPath 'assets\bin' -Force; Remove-Item 'bin_temp.zip' -Force"
:STEP4
:: 4. Buat Launcher & Shortcut Desktop
echo [4/4] Membuat launcher dan shortcut Desktop...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$vbs = @('Set fso = CreateObject(\"Scripting.FileSystemObject\")', 'dir = fso.GetParentFolderName(WScript.ScriptFullName)', 'Set sh = CreateObject(\"WScript.Shell\")', 'sh.CurrentDirectory = dir', 'sh.Run \"\"\"\" & dir & \"\runtime_python\pythonw.exe\"\" \"\"\" & dir & \"\main.py\"\"\", 0, False'); $vbs | Set-Content -Encoding ASCII 'Jalankan_AutoHardsub.vbs'; $ws = New-Object -ComObject WScript.Shell; $sc = $ws.CreateShortcut(\"$env:USERPROFILE\Desktop\AutoHardsub.lnk\"); $sc.TargetPath = 'wscript.exe'; $sc.Arguments = '\"%INSTALL_DIR%\Jalankan_AutoHardsub.vbs\"'; $sc.WorkingDirectory = '%INSTALL_DIR%'; $sc.IconLocation = 'shell32.dll,115'; $sc.Save()"

powershell -NoProfile -ExecutionPolicy Bypass -Command "$ws = New-Object -ComObject WScript.Shell; $sc = $ws.CreateShortcut(\"$env:USERPROFILE\Desktop\AutoHardsub.lnk\"); $sc.TargetPath = 'wscript.exe'; $sc.Arguments = '\"%INSTALL_DIR%\Jalankan_AutoHardsub.vbs\"'; $sc.WorkingDirectory = '%INSTALL_DIR%'; $sc.IconLocation = 'shell32.dll,115'; $sc.Save()"

echo.
echo ========================================================
echo   INSTALASI SELESAI! Membuka AutoHardsub...
echo   Shortcut sudah dibuat di Desktop: AutoHardsub
echo ========================================================
timeout /t 2 >nul
start "" wscript.exe "%INSTALL_DIR%\Jalankan_AutoHardsub.vbs"
exit