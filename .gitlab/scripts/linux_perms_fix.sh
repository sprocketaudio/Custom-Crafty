#!/bin/bash

# Prompt the user for the directory path
read -p "Enter the directory path to set permissions (/var/opt/minecraft/crafty): " directory_path

# Count the total number of directories
total_dirs=$(find "$directory_path" -type d 2>/dev/null | wc -l)

# Count the total number of files
total_files=$(find "$directory_path" -type f 2>/dev/null | wc -l)

# Initialize a counter for directories and files
dir_count=0
file_count=0

# Function to print progress
print_progress() {
    echo -ne "\rDirectories: $dir_count/$total_dirs Files: $file_count/$total_files"
}

# Check if the script is running within a Docker container
if [ -f "/.dockerenv" ]; then
    echo "Script is running within a Docker container. Exiting with error."
    exit 1  # Exit with an error code if running in Docker
else
    echo "Script is not running within a Docker container. Executing permissions changes..."

    # Run the commands to set permissions for directories
    echo "Changing permissions for directories:"
    for dir in $(find "$directory_path" -type d 2>/dev/null); do
        if [ -e "$dir" ]; then
            sudo chmod 700 "$dir" && ((dir_count++))
        fi
        print_progress
    done

    # Run the commands to set permissions for files
    echo -e "\nChanging permissions for files:"
    for file in $(find "$directory_path" -type f 2>/dev/null); do
        if [ -e "$file" ]; then
            sudo chmod 644 "$file" && ((file_count++))
        fi
        print_progress
    done
    echo "You will now need to execute a chmod +x on all bedrock executables"
fi

echo ""  # Adding a new line after the loop for better readability