@echo off
REM Atualiza o estoque: ingere do Google Drive e publica no servidor.
REM Basta dar duplo-clique neste arquivo.
cd /d "%~dp0"
echo Atualizando estoque (Drive -^> servidor)...
echo.
python -m scripts.atualizar
echo.
echo ================================================
echo Concluido. Pode fechar esta janela.
pause
