@echo off
rem Runs Python with uv's base interpreter and this project's installed packages.
rem
rem Use it when Windows Smart App Control blocks .venv\Scripts\python.exe (the launcher uv
rem creates is unsigned), which makes every "uv run ..." command fail with
rem "An Application Control policy has blocked this file". The base interpreter is allowed.
rem
rem   scripts\py.cmd -m uvicorn api.main:app --port 8000
rem   scripts\py.cmd -m pytest -q
setlocal
for /f "delims=" %%d in ('uv python dir') do set "UV_PYTHON_DIR=%%d"
set "PYTHONPATH=%~dp0..\.venv\Lib\site-packages"
"%UV_PYTHON_DIR%\cpython-3.12-windows-x86_64-none\python.exe" %*
exit /b %ERRORLEVEL%
