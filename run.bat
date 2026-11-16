@echo off
REM ============================================================
REM run.bat — Khoi dong Smart DRL Assistant (Windows)
REM Tao venv (neu chua co) -> cai dependencies -> chay Streamlit
REM ============================================================
setlocal
cd /d "%~dp0"

if not exist "venv\" (
    echo [run] Tao moi truong ao venv...
    python -m venv venv
    if errorlevel 1 (
        echo [run] LOI: khong tao duoc venv. Kiem tra Python da cai va co trong PATH.
        exit /b 1
    )
)

echo [run] Cai dat dependencies...
"venv\Scripts\python.exe" -m pip install --upgrade pip >nul
"venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
    echo [run] LOI: cai dat thu vien that bai.
    exit /b 1
)

echo [run] Seed du lieu mau (neu DB trong)...
"venv\Scripts\python.exe" -m drl.seed_data

echo [run] Khoi dong ung dung tai http://localhost:8501
"venv\Scripts\python.exe" -m streamlit run app.py --server.port=8501
endlocal
