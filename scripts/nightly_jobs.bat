@echo off
REM ============================================================
REM  LM-MonoLithic — Nightly maintenance jobs
REM  Run via Windows Task Scheduler at 00:05 every day.
REM
REM  Setup:
REM   1. Open Task Scheduler → Create Basic Task
REM   2. Trigger: Daily at 00:05
REM   3. Action: Start a program → browse to this file
REM   4. "Start in" must be set to the Backend\ folder
REM
REM  Or run manually from Backend\:
REM   scripts\nightly_jobs.bat
REM ============================================================

SETLOCAL

REM ── Paths ───────────────────────────────────────────────────
SET BACKEND_DIR=%~dp0..
SET PYTHON=python

REM ── Log file (appended daily) ────────────────────────────────
SET LOGFILE=%BACKEND_DIR%\scripts\nightly_jobs.log

echo. >> "%LOGFILE%"
echo ============================================================ >> "%LOGFILE%"
echo [%DATE% %TIME%] Starting nightly jobs >> "%LOGFILE%"
echo ============================================================ >> "%LOGFILE%"

cd /d "%BACKEND_DIR%"

REM ── 1. Expire leases past their expiry_date ─────────────────
echo [%DATE% %TIME%] Running expire_leases... >> "%LOGFILE%"
%PYTHON% manage.py expire_leases >> "%LOGFILE%" 2>&1
IF %ERRORLEVEL% NEQ 0 (
    echo [%DATE% %TIME%] ERROR: expire_leases failed (exit code %ERRORLEVEL%) >> "%LOGFILE%"
) ELSE (
    echo [%DATE% %TIME%] expire_leases OK >> "%LOGFILE%"
)

REM ── 2. Generate scheduled invoices ──────────────────────────
echo [%DATE% %TIME%] Running generate_scheduled_invoices... >> "%LOGFILE%"
%PYTHON% manage.py generate_scheduled_invoices >> "%LOGFILE%" 2>&1
IF %ERRORLEVEL% NEQ 0 (
    echo [%DATE% %TIME%] ERROR: generate_scheduled_invoices failed (exit code %ERRORLEVEL%) >> "%LOGFILE%"
) ELSE (
    echo [%DATE% %TIME%] generate_scheduled_invoices OK >> "%LOGFILE%"
)

REM ── 3. Process overdue invoices ──────────────────────────────
echo [%DATE% %TIME%] Running process_overdue_invoices... >> "%LOGFILE%"
%PYTHON% manage.py process_overdue_invoices >> "%LOGFILE%" 2>&1
IF %ERRORLEVEL% NEQ 0 (
    echo [%DATE% %TIME%] ERROR: process_overdue_invoices failed (exit code %ERRORLEVEL%) >> "%LOGFILE%"
) ELSE (
    echo [%DATE% %TIME%] process_overdue_invoices OK >> "%LOGFILE%"
)

REM ── 4. Refresh AR summaries ──────────────────────────────────
echo [%DATE% %TIME%] Running update_ar_summary... >> "%LOGFILE%"
%PYTHON% manage.py update_ar_summary >> "%LOGFILE%" 2>&1
IF %ERRORLEVEL% NEQ 0 (
    echo [%DATE% %TIME%] ERROR: update_ar_summary failed (exit code %ERRORLEVEL%) >> "%LOGFILE%"
) ELSE (
    echo [%DATE% %TIME%] update_ar_summary OK >> "%LOGFILE%"
)

echo [%DATE% %TIME%] Nightly jobs complete. >> "%LOGFILE%"
ENDLOCAL
