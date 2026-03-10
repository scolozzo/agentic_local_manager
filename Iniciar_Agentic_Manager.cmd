@echo off
setlocal

set "REPO_DIR=C:\Trabajo\AgenticLocalManager_Proyect"
set "DASHBOARD_PORT=8888"
set "DASHBOARD_URL=http://localhost:%DASHBOARD_PORT%"
set "DASHBOARD_HEALTH_URL=http://127.0.0.1:%DASHBOARD_PORT%/"

cd /d "%REPO_DIR%" || (
  echo No se pudo acceder al repositorio: %REPO_DIR%
  pause
  exit /b 1
)

set "PYTHON_EXE="
set "PYTHON_ARGS="
where py >nul 2>nul && (
  set "PYTHON_EXE=py"
  set "PYTHON_ARGS=-3"
)
if not defined PYTHON_EXE (
  where python >nul 2>nul && set "PYTHON_EXE=python"
)

if not defined PYTHON_EXE (
  echo No se encontro Python en PATH.
  echo Instala Python o agrega el ejecutable a PATH antes de iniciar el sistema.
  pause
  exit /b 1
)

call :check_dashboard
if errorlevel 1 (
  echo Iniciando dashboard en %DASHBOARD_URL% ...
  start "Agentic Manager Dashboard" /D "%REPO_DIR%" "%PYTHON_EXE%" %PYTHON_ARGS% dashboard.py
  call :wait_dashboard
  if errorlevel 1 (
    echo El dashboard no respondio correctamente en %DASHBOARD_URL%.
    echo Ejecuta manualmente: cd /d "%REPO_DIR%" ^&^& "%PYTHON_EXE%" %PYTHON_ARGS% dashboard.py
    pause
    exit /b 1
  )
) else (
  echo El dashboard ya estaba corriendo y responde en %DASHBOARD_URL%.
)

start "" %DASHBOARD_URL%
exit /b 0

:check_dashboard
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "try { $r = Invoke-WebRequest -UseBasicParsing '%DASHBOARD_HEALTH_URL%' -TimeoutSec 3; if ($r.StatusCode -eq 200) { exit 0 } else { exit 1 } } catch { exit 1 }"
exit /b %errorlevel%

:wait_dashboard
for /l %%I in (1,1,20) do (
  call :check_dashboard
  if not errorlevel 1 exit /b 0
  timeout /t 1 /nobreak >nul
)
exit /b 1
