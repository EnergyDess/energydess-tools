@echo off
cd /d "%~dp0"
echo.
echo  ================================
echo   EnergyDess Tools — запуск...
echo  ================================
echo.
echo  Открой браузер: http://localhost:8000
echo.
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
pause
