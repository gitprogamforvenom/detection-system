@echo off
chcp 65001 >nul
setlocal

set ROOT=%~dp0
set FRAUD=%ROOT%pbi card
set SPAM=%ROOT%Spam-Detection-Classifier-main\Spam-Detection-Classifier-main\spam_detection
set GATE=%ROOT%launcher

echo.
echo =====================================================
echo    SentinelLedger -- Starting All Services
echo =====================================================
echo.
echo ROOT : %ROOT%
echo FRAUD: %FRAUD%
echo SPAM : %SPAM%
echo GATE : %GATE%
echo.

echo [1/3] Starting FraudGuard on port 5000...
start "FraudGuard-5000" cmd /k "cd /d "%FRAUD%" && python app.py"

echo      Waiting 6 seconds for FraudGuard...
timeout /t 6 /nobreak >nul

echo [2/3] Starting SpamShield on port 5001...
start "SpamShield-5001" cmd /k "cd /d "%SPAM%" && python manage.py runserver 5001 --noreload"

echo      Waiting 6 seconds for SpamShield...
timeout /t 6 /nobreak >nul

echo [3/3] Starting Gateway + Auth on port 8000...
start "Gateway-8000" cmd /k "cd /d "%GATE%" && python serve.py"

echo      Waiting 4 seconds for Gateway...
timeout /t 4 /nobreak >nul

echo.
echo =====================================================
echo   ALL SERVICES STARTED
echo.
echo   LOGIN    : http://localhost:8000/login
echo   REGISTER : http://localhost:8000/register
echo   DASHBOARD: http://localhost:8000/dashboard
echo   FRAUDGUARD (after login): http://localhost:8000/fraud/
echo   SPAMSHIELD (after login): http://localhost:8000/spam/
echo.
echo   NOTE: Without login /fraud and /spam are BLOCKED
echo =====================================================
echo.

start http://localhost:8000/login

endlocal
