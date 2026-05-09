@echo off
REM =====================================================================
REM  Zucchetti Agent — Aggiornamento automatico dal repo GitHub
REM  Da copiare/eseguire in C:\zucchetti-agent\
REM
REM  Cosa fa:
REM   1) Ferma il servizio Windows ZucchettiAgent
REM   2) Backup zucchetti_agent.py corrente con timestamp
REM   3) Download ultima versione da GitHub (raw)
REM   4) Riavvio servizio
REM   5) Verifica stato finale
REM
REM  I file .bak_YYYYMMDD_HHmm si accumulano in C:\zucchetti-agent\,
REM  cancellali manualmente di tanto in tanto se non ti servono.
REM =====================================================================

setlocal
cd /d C:\zucchetti-agent

echo.
echo ====================================================
echo  AGGIORNAMENTO ZUCCHETTI AGENT
echo ====================================================
echo.

echo [1/5] Stop servizio ZucchettiAgent...
python zucchetti_agent.py stop
timeout /t 3 /nobreak >nul

echo.
echo [2/5] Backup file corrente...
if exist zucchetti_agent.py (
    REM Costruisci timestamp YYYYMMDD_HHmm in modo locale-safe
    for /f "tokens=2 delims==" %%I in ('"wmic os get localdatetime /value"') do set DT=%%I
    set TS=!DT:~0,8!_!DT:~8,4!
    powershell -NoProfile -Command "$ts=(Get-Date).ToString('yyyyMMdd_HHmm'); Move-Item -LiteralPath 'C:\zucchetti-agent\zucchetti_agent.py' -Destination ('C:\zucchetti-agent\zucchetti_agent.py.bak_'+$ts) -Force"
    echo Backup salvato.
) else (
    echo Nessun file precedente trovato (prima installazione?)
)

echo.
echo [3/5] Download ultima versione da GitHub...
powershell -NoProfile -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri 'https://raw.githubusercontent.com/italiapaghe-visitatori/visitor-registration-system/master/zucchetti_agent.py' -OutFile 'C:\zucchetti-agent\zucchetti_agent.py' -UseBasicParsing"
if not exist zucchetti_agent.py (
    echo ERRORE: download fallito! Ripristino dall'ultimo backup...
    powershell -NoProfile -Command "$last = Get-ChildItem 'C:\zucchetti-agent\zucchetti_agent.py.bak_*' | Sort-Object LastWriteTime -Descending | Select-Object -First 1; if ($last) { Copy-Item $last.FullName -Destination 'C:\zucchetti-agent\zucchetti_agent.py' }"
    goto :restart
)
for %%A in (zucchetti_agent.py) do echo File scaricato: %%~zA bytes

:restart
echo.
echo [4/5] Restart servizio...
python zucchetti_agent.py start
timeout /t 4 /nobreak >nul

echo.
echo [5/5] Verifica stato:
sc query ZucchettiAgent | findstr /C:"STATO"

echo.
echo ====================================================
echo  FATTO. Controlla che lo stato sia "4 RUNNING".
echo  Se vedi START_PENDING, ricontrolla tra 10 secondi
echo  con: sc query ZucchettiAgent
echo ====================================================
echo.
pause
endlocal
