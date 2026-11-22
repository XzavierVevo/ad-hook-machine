#!/bin/bash

# Ad Hook Generation Bot - Mac Launcher Script
# Double-click this file to run the bot

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Change to the script directory
cd "$SCRIPT_DIR"

# Activate virtual environment if it exists
if [ -d "venv" ]; then
    source venv/bin/activate
elif [ -d ".venv" ]; then
    source .venv/bin/activate
fi

# Check if Python 3 is available
if ! command -v python3 &> /dev/null; then
    echo "Error: Python 3 is not installed or not in PATH"
    echo "Please install Python 3 and try again"
    read -p "Press Enter to exit..."
    exit 1
fi

# Run the bot
echo "Starting Ad Hook Generation Bot..."
echo ""
python3 -m hook_generator.main

# Keep terminal open if there's an error
if [ $? -ne 0 ]; then
    echo ""
    echo "Bot exited with an error."
    read -p "Press Enter to close..."
fi

