@echo off
echo ===============================
echo INICIANDO IMPERIO ERP
echo ===============================

REM --server.runOnSave: refresca al guardar
REM --server.fileWatcherType=auto: detecta cambios de archivos en más entornos
py -m streamlit run app.py --server.runOnSave true --server.fileWatcherType auto

echo.
echo Si hubo un error revisa arriba.
pause
