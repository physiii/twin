#!/bin/bash

# Install necessary packages
echo "Installing required packages..."
sudo apt-get install -y portaudio19-dev xdotool playerctl python3-venv gnome-screenshot
if [ $? -eq 0 ]; then
    echo "Package installation successful."
else
    echo "Package installation failed." >&2
    exit 1
fi

# Get the current username and UID
username=$(whoami)
userid=$(id -u "$username")
home_dir=$(eval echo ~$username)
venv_dir="$home_dir/venv"
script_dir="/media/mass/scripts/twin"
systemd_user_dir="$home_dir/.config/systemd/user"
env_file="$systemd_user_dir/twin.env"
service_file="$systemd_user_dir/twin.service"

echo "Setting up virtual environment in: $venv_dir"
python3 -m venv "$venv_dir"
if [ $? -eq 0 ]; then
    echo "Virtual environment created successfully."
else
    echo "Failed to create virtual environment." >&2
    exit 1
fi

echo "Activating virtual environment and installing requirements..."
source "$venv_dir/bin/activate"
pip install --upgrade pip
pip install -r "$script_dir/requirements.txt"
if [ $? -eq 0 ]; then
    echo "Requirements installed successfully."
else
    echo "Failed to install requirements." >&2
    deactivate
    exit 1
fi
deactivate

echo "Setting up service for user: $username (UID: $userid)"

# Create necessary directories
echo "Creating systemd user directory: $systemd_user_dir"
mkdir -p "$systemd_user_dir"
if [ $? -eq 0 ]; then
    echo "Directory created: $systemd_user_dir"
else
    echo "Failed to create directory: $systemd_user_dir" >&2
    exit 1
fi

# Create environment file
echo "Creating environment file: $env_file"
cat > "$env_file" <<EOF
PULSE_SERVER=unix:/run/user/$userid/pulse/native
DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$userid/bus
DISPLAY=:0
XAUTHORITY=$home_dir/.Xauthority
EOF
if [ $? -eq 0 ]; then
    echo "Environment file created: $env_file"
else
    echo "Failed to create environment file: $env_file" >&2
    exit 1
fi

# Create systemd service file
echo "Creating systemd service file: $service_file"
cat > "$service_file" <<EOF
[Unit]
Description=Twin Script Service
After=default.target sound.target graphical-session.target
Wants=sound.target graphical-session.target

[Service]
Type=simple
ExecStart=/usr/bin/env bash -c 'source $venv_dir/bin/activate && python $script_dir/main.py --source pulse -e --local-embed 192.168.1.42 --local-inference 192.168.1.42 --store-ip 192.168.1.42 --silent'
WorkingDirectory=$script_dir
EnvironmentFile=$env_file
Environment="GPT4O_API_KEY=$(os.environ.get('OPENAI_API_KEY'))"
Restart=always
RestartSec=10

[Install]
WantedBy=default.target
EOF
if [ $? -eq 0 ]; then
    echo "Service file created: $service_file"
else
    echo "Failed to create service file: $service_file" >&2
    exit 1
fi

# Reload the systemd user daemon and enable the service for the current user
echo "Reloading systemd user daemon for user: $username"
systemctl --user daemon-reload
if [ $? -eq 0 ]; then
    echo "Systemd user daemon reloaded successfully for user: $username"
else
    echo "Failed to reload systemd user daemon for user: $username" >&2
    exit 1
fi

echo "Enabling service for user: $username"
systemctl --user enable twin.service
if [ $? -eq 0 ]; then
    echo "Service enabled successfully for user: $username"
else
    echo "Failed to enable service for user: $username" >&2
    exit 1
fi

echo "Setup complete for user: $username."
