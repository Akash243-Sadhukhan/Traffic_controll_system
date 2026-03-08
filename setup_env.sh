#!/bin/bash

# Detect OS
OS="$(uname)"
if [ "$OS" == "Darwin" ]; then
    echo "Detected macOS"
    PYTHON_CMD="python3"
    VENV_DIR="venv"
    ACTIVATE_SCRIPT="source $VENV_DIR/bin/activate"
elif [ "$(expr substr $(uname -s) 1 5)" == "Linux" ]; then
    echo "Detected Linux"
    PYTHON_CMD="python3"
    VENV_DIR="venv"
    ACTIVATE_SCRIPT="source $VENV_DIR/bin/activate"
elif [ "$(expr substr $(uname -s) 1 10)" == "MINGW32_NT" ] || [ "$(expr substr $(uname -s) 1 10)" == "MINGW64_NT" ]; then
    echo "Detected Windows (Git Bash)"
    PYTHON_CMD="python"
    VENV_DIR="venv"
    ACTIVATE_SCRIPT="source $VENV_DIR/Scripts/activate"
else
    echo "Unknown OS. Assuming Unix-like..."
    PYTHON_CMD="python3"
    VENV_DIR="venv"
    ACTIVATE_SCRIPT="source $VENV_DIR/bin/activate"
fi

# Create Virtual Environment if it doesn't exist
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment..."
    $PYTHON_CMD -m venv $VENV_DIR
fi

# Activate Virtual Environment
echo "Activating virtual environment..."
$ACTIVATE_SCRIPT

# Install Requirements
if [ -f "requirements.txt" ]; then
<<<<<<< HEAD
    echo "Installing dependencies..."
=======
    echo "Installing root dependencies..."
>>>>>>> 48bccc1 (incomplete test files)
    pip install -r requirements.txt
else
    echo "requirements.txt not found!"
fi

<<<<<<< HEAD
=======
# Install AI-services Requirements
if [ -f "ai-services/requirements.txt" ]; then
    echo "Installing AI-services dependencies..."
    pip install -r ai-services/requirements.txt
else
    echo "ai-services/requirements.txt not found!"
fi

>>>>>>> 48bccc1 (incomplete test files)
echo "Setup complete! To activate the environment manually, run:"
echo "$ACTIVATE_SCRIPT"
