@echo off
echo ===================================================
echo   Voronoi Works - Quartz Local Preview Server
echo ===================================================
echo.

where npx >nul 2>nul
if %errorlevel% equ 0 goto RUN_SERVER

if exist "C:\Program Files\Unity\Hub\Editor\6000.4.6f1\Editor\Data\PlaybackEngines\WebGLSupport\BuildTools\Emscripten\node\npx.cmd" (
    set "PATH=C:\Program Files\Unity\Hub\Editor\6000.4.6f1\Editor\Data\PlaybackEngines\WebGLSupport\BuildTools\Emscripten\node;%PATH%"
    goto RUN_SERVER
)

if exist "C:\Users\sgtko\AppData\Local\Autodesk\webdeploy\production\257040cabc1dffce734a8079453b19b0ffe2b735\NODEJS\npx.cmd" (
    set "PATH=C:\Users\sgtko\AppData\Local\Autodesk\webdeploy\production\257040cabc1dffce734a8079453b19b0ffe2b735\NODEJS;%PATH%"
    goto RUN_SERVER
)

if exist "C:\Users\sgtko\AppData\Local\OpenAI\Codex\runtimes\cua_node\f1bf3cd3a5929acd\bin\npx.cmd" (
    set "PATH=C:\Users\sgtko\AppData\Local\OpenAI\Codex\runtimes\cua_node\f1bf3cd3a5929acd\bin;%PATH%"
    goto RUN_SERVER
)

echo [ERROR] Node.js / npx not found.
echo Please install Node.js (LTS) from https://nodejs.org/
echo.
pause
exit /b 1

:RUN_SERVER
echo [SUCCESS] Node.js environment ready!
echo Starting local server at http://localhost:8080 ...
echo (Save markdown files in content/ to see instant live preview)
echo.
echo Press Ctrl+C in this window when you want to stop.
echo.
cd /d "%~dp0.."
call npx tsx ./quartz/bootstrap-cli.mjs build --serve
pause
