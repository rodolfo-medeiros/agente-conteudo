@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title SETUP - Agente de Conteudo

echo.
echo ==============================================================
echo   SETUP DO AGENTE DE CONTEUDO  (Windows)
echo.
echo   Este script:
echo     1. Baixa um Python 3.12 PORTATIL para a pasta runtime\
echo        (nao interfere com nenhum Python ja instalado)
echo     2. Habilita o pip nesse Python portatil
echo     3. Instala as dependencias do requirements.txt
echo     4. Gera o .env a partir do .env.example (se nao existir)
echo     5. Gera o launcher iniciar_agente.bat (se nao existir)
echo.
echo   Pasta do projeto: %~dp0
echo   Tempo estimado: 5 a 15 minutos (conforme a internet)
echo ==============================================================
echo.

REM ------------------------------------------------------------
REM Guarda de idempotencia: ambiente ja configurado?
REM ------------------------------------------------------------
if exist "venv\Scripts\python.exe" goto ambiente_venv
if exist "runtime\python.exe" goto ambiente_runtime
goto comecar

:ambiente_venv
echo Ambiente venv\ ja configurado - nada a fazer.
echo Use iniciar_agente.bat para abrir o painel.
echo.
pause
exit /b 0

:ambiente_runtime
echo Ambiente runtime\ ja configurado - nada a fazer.
echo Use iniciar_agente.bat para abrir o painel.
echo.
pause
exit /b 0

:comecar
where curl.exe >nul 2>nul
if not errorlevel 1 goto curl_ok
echo ERRO: curl.exe nao encontrado. Este setup funciona no Windows 10
echo       atualizacao 1803 ou superior. Atualize o Windows e rode de novo.
echo.
pause
exit /b 1

:curl_ok
REM ------------------------------------------------------------
REM 1. Python portatil
REM ------------------------------------------------------------
echo [1/5] Baixando Python 3.12.10 portatil (~11 MB) para runtime\ ...
curl.exe -L -o python_embed.zip "https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip"
if not errorlevel 1 goto download_ok
echo ERRO: falha no download do Python. Verifique a internet e rode de novo.
echo.
pause
exit /b 1

:download_ok
if exist "python_embed.zip" goto zip_ok
echo ERRO: python_embed.zip nao encontrado apos o download.
echo.
pause
exit /b 1

:zip_ok
echo       Extraindo ...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Expand-Archive -Path 'python_embed.zip' -DestinationPath 'runtime' -Force"
if exist "runtime\python.exe" goto extract_ok
echo ERRO: runtime\python.exe nao encontrado apos a extracao.
echo.
pause
exit /b 1

:extract_ok
del python_embed.zip >nul 2>nul

REM ------------------------------------------------------------
REM 2. pip no Python portatil
REM ------------------------------------------------------------
echo [2/5] Habilitando pip no Python portatil ...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Add-Content -Path 'runtime\python312._pth' -Value 'import site','..'"
curl.exe -L -o get-pip.py "https://bootstrap.pypa.io/get-pip.py"
if exist "get-pip.py" goto getpip_ok
echo ERRO: falha no download do get-pip.py.
echo.
pause
exit /b 1

:getpip_ok
"runtime\python.exe" get-pip.py --no-warn-script-location
if not errorlevel 1 goto pip_ok
echo ERRO: falha ao instalar o pip. Verifique o erro acima.
echo.
pause
exit /b 1

:pip_ok
del get-pip.py >nul 2>nul

REM ------------------------------------------------------------
REM 3. Dependencias + verificacao
REM ------------------------------------------------------------
echo [3/5] Instalando as dependencias (5 a 15 min) ...
"runtime\python.exe" -m pip install --no-warn-script-location -r requirements.txt
if not errorlevel 1 goto deps_instalados
echo ERRO: falha ao instalar as dependencias. Verifique o erro acima.
echo.
pause
exit /b 1

:deps_instalados
echo       Verificando os modulos principais ...
"runtime\python.exe" -c "import streamlit, chromadb, langchain_classic, langchain_community, langchain_chroma, langchain_google_genai, dotenv, google_auth_oauthlib, googleapiclient, photoshop, pymupdf, reportlab; print('OK - modulos carregados')"
if not errorlevel 1 goto verif_ok
echo AVISO: instalacao concluida mas a verificacao falhou - verifique o erro
echo        acima antes da primeira execucao.
goto verif_fim

:verif_ok
echo       OK - instalacao validada.

:verif_fim

REM ------------------------------------------------------------
REM 4. .env
REM ------------------------------------------------------------
if exist ".env" goto env_ok
if exist ".env.example" goto env_exemplo
echo [4/5] AVISO: .env.example nao encontrado - crie o .env manualmente.
goto env_fim

:env_exemplo
copy /y ".env.example" ".env" >nul
echo [4/5] .env gerado a partir do .env.example.
echo       Preencha GOOGLE_API_KEY e GOOGLE_DRIVE_FOLDER_ID (veja ONBOARDING.md).
goto env_fim

:env_ok
echo [4/5] .env ja existe - mantido.

:env_fim

REM ------------------------------------------------------------
REM 5. Launcher
REM ------------------------------------------------------------
if exist "iniciar_agente.bat" goto launcher_ok
(
echo @echo off
echo cd /d "%~dp0"
echo runtime\python.exe -m streamlit run app.py
echo pause
) > iniciar_agente.bat
echo [5/5] Launcher iniciar_agente.bat gerado.
goto fim

:launcher_ok
echo [5/5] Launcher iniciar_agente.bat ja existe.

:fim
echo.
echo ==============================================================
echo   SETUP CONCLUIDO!
echo.
echo   Proximos passos (detalhes no ONBOARDING.md):
echo     1. Baixe os PDFs da base para a pasta knowledge_base\
echo     2. Copie o system_prompt_token.md para a raiz do projeto
echo     3. Garanta o oauth_credentials.json na raiz do projeto
echo     4. Preencha o .env (GOOGLE_API_KEY e GOOGLE_DRIVE_FOLDER_ID)
echo     5. Rode iniciar_agente.bat - na primeira vez o navegador
echo        abrira para autorizar o acesso ao Google (sua conta)
echo ==============================================================
echo.
pause
