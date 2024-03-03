#!/bin/bash

# Prompt the user for the directory path
read -p "Enter the directory path to set permissions (/var/opt/minecraft/crafty): " directory_path

# Check if the script is running within a Docker container
if [ -f "/.dockerenv" ]; then
    echo "Script is running within a Docker container. Exiting with error."
    exit 1  # Exit with an error code if running in Docker
else
    echo "Script is not running within a Docker container. Executing permissions changes..."
    # Run the commands to set permissions
    sudo chmod 700 $(find "$directory_path" -type d)
    sudo chmod 644 $(find "$directory_path" -type f)
fi