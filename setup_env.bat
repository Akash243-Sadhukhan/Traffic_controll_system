@echo off
echo Detected Windows

set VENV_DIR=venv

:: Create Virtual Environment if it doesn't exist
if not exist %VENV_DIR% (
    echo Creating virtual environment...
    python -m venv %VENV_DIR%
)

:: Activate Virtual Environment
echo Activating virtual environment...
call %VENV_DIR%\Scripts\activate.bat

:: Install Requirements
if exist requirements.txt (
    echo Installing dependencies...
    pip install -r requirements.txt
) else (
    echo requirements.txt not found!
)

echo Setup complete! To activate the environment manually, run:
echo %VENV_DIR%\Scripts\activate.bat
pause
