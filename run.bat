@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
cd /d "%~dp0"
title Smart DRL Assistant - HCMUS

echo ==========================================================
echo    Smart DRL Assistant - HCMUS  ^|  Phien ban 2.0.0-CRAWLER
echo    (co tab "Thu thap TU DONG" tu web truong)
echo ==========================================================
echo.
echo   Thu muc dang chay: %CD%
if not exist "drl\crawler.py" (
    echo.
    echo   [CANH BAO] Thu muc nay THIEU file drl\crawler.py
    echo   => Day KHONG phai ban moi nhat. Ban se khong thay tab Thu thap TU DONG.
    echo   Hay dong cua so nay, giai nen lai file zip vao thu muc KHAC roi chay lai.
    echo.
    pause
    exit /b 1
)
echo   [OK] Da tim thay bo thu thap tu dong drl\crawler.py
echo.

echo [1/4] Kiem tra Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo   [LOI] Chua cai Python hoac Python chua co trong PATH.
    echo   Tai tai: https://www.python.org/downloads/
    echo   Khi cai nho TICK vao o "Add python.exe to PATH".
    echo.
    pause
    exit /b 1
)
for /f "delims=" %%v in ('python --version 2^>^&1') do echo       Da tim thay: %%v

echo [2/4] Cai thu vien - lan dau mat 1-3 phut, cac lan sau rat nhanh...
python -m pip install --quiet --no-warn-script-location --disable-pip-version-check streamlit pandas networkx scikit-learn matplotlib google-generativeai openpyxl requests
if errorlevel 1 (
    echo.
    echo   [LOI] Cai thu vien that bai. Kiem tra ket noi mang roi chay lai file nay.
    echo.
    pause
    exit /b 1
)
echo       Xong.

echo [3/4] Tat man hinh chao moi cua Streamlit de khong phai bam Enter...
if not exist "%USERPROFILE%\.streamlit" mkdir "%USERPROFILE%\.streamlit" >nul 2>&1
if not exist "%USERPROFILE%\.streamlit\credentials.toml" (
    > "%USERPROFILE%\.streamlit\credentials.toml" echo [general]
    >> "%USERPROFILE%\.streamlit\credentials.toml" echo email = ""
)
echo       Xong.

echo [4/4] Khoi dong ung dung...
echo.
echo       URL: http://localhost:8501
echo       Trinh duyet se TU MO khi server san sang ^(co the mat 5-20 giay^).
echo       De DUNG server: bam Ctrl+C trong cua so nay.
echo.
echo ----------------------------------------------------------

rem Cho toi khi server tra ve HTTP 200 roi moi mo trinh duyet
start "" powershell -NoProfile -WindowStyle Hidden -Command ^
  "$u='http://localhost:8501'; for($i=0;$i -lt 180;$i++){ try{ $r=Invoke-WebRequest -Uri $u -UseBasicParsing -TimeoutSec 2; if($r.StatusCode -eq 200){ Start-Process $u; break } }catch{}; Start-Sleep -Milliseconds 1000 }"

python -m streamlit run app.py --server.headless true --server.port 8501 --browser.gatherUsageStats false

echo.
echo ==========================================================
echo   Server da dung. Neu gap loi "Port 8501 is already in use",
echo   doi sang cong khac:  python -m streamlit run app.py --server.port 8502
echo ==========================================================
pause
