@echo off
setlocal
cd /d D:\Quant\AStockLab
call C:\Users\10770\miniconda3\Scripts\activate.bat qlib
if errorlevel 1 (
  echo [AStockLab] Failed to activate the qlib environment.
  pause
  exit /b 1
)
set PYTHONUTF8=1
set MLFLOW_DISABLE_AGENT_HINT=1
python -m streamlit run app.py --server.headless false --browser.gatherUsageStats false
if errorlevel 1 pause
endlocal

