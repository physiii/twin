#!/bin/bash
# Setup script for Twin RTSP Microphone Server

set -e  # Exit on any error

echo "🤖 Twin RTSP Microphone Server Setup"
echo "===================================="
echo

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}✅${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠️${NC} $1"
}

print_error() {
    echo -e "${RED}❌${NC} $1"
}

print_info() {
    echo -e "${BLUE}ℹ️${NC} $1"
}

# Detect package manager
detect_package_manager() {
    if command -v apt &> /dev/null; then
        echo "apt"
    elif command -v dnf &> /dev/null; then
        echo "dnf"
    elif command -v yum &> /dev/null; then
        echo "yum"
    elif command -v pacman &> /dev/null; then
        echo "pacman"
    else
        echo "unknown"
    fi
}

# Install packages based on package manager
install_packages() {
    local pkg_manager=$1
    
    print_info "Installing required packages..."
    
    case $pkg_manager in
        "apt")
            sudo apt update
            sudo apt install -y ffmpeg pulseaudio-utils python3 python3-pip
            ;;
        "dnf")
            sudo dnf install -y ffmpeg pulseaudio-utils python3 python3-pip
            ;;
        "yum")
            # Enable EPEL for FFmpeg
            sudo yum install -y epel-release
            sudo yum install -y ffmpeg pulseaudio-utils python3 python3-pip
            ;;
        "pacman")
            sudo pacman -S --needed ffmpeg pulseaudio python python-pip
            ;;
        *)
            print_error "Unknown package manager. Please install manually:"
            echo "  - ffmpeg"
            echo "  - pulseaudio-utils"
            echo "  - python3"
            echo "  - python3-pip"
            return 1
            ;;
    esac
}

# Check if running on supported system
check_system() {
    if [[ "$OSTYPE" != "linux-gnu"* ]]; then
        print_error "This script is designed for Linux systems"
        exit 1
    fi
    
    print_status "System check passed"
}

# Check dependencies
check_dependencies() {
    print_info "Checking dependencies..."
    
    local missing_deps=()
    
    # Check FFmpeg
    if ! command -v ffmpeg &> /dev/null; then
        missing_deps+=("ffmpeg")
    else
        print_status "FFmpeg found: $(ffmpeg -version | head -n1 | cut -d' ' -f3)"
    fi
    
    # Check Python
    if ! command -v python3 &> /dev/null; then
        missing_deps+=("python3")
    else
        print_status "Python found: $(python3 --version | cut -d' ' -f2)"
    fi
    
    # Check PulseAudio tools
    if ! command -v pactl &> /dev/null; then
        missing_deps+=("pulseaudio-utils")
    else
        print_status "PulseAudio tools found"
    fi
    
    if [ ${#missing_deps[@]} -ne 0 ]; then
        print_warning "Missing dependencies: ${missing_deps[*]}"
        return 1
    fi
    
    return 0
}

# Test audio system
test_audio() {
    print_info "Testing audio system..."
    
    # Check if PulseAudio/PipeWire is running
    if ! pgrep -x "pulseaudio\|pipewire" > /dev/null; then
        print_warning "PulseAudio/PipeWire not running. Starting PulseAudio..."
        pulseaudio --start --daemonize || true
    fi
    
    # List audio sources
    if pactl list short sources &> /dev/null; then
        local source_count=$(pactl list short sources | wc -l)
        print_status "Found $source_count audio source(s)"
        
        print_info "Available audio sources:"
        pactl list short sources | while read line; do
            echo "  - $line"
        done
    else
        print_warning "Could not list audio sources"
    fi
}

# Test RTSP server
test_rtsp_server() {
    print_info "Testing RTSP microphone server..."
    
    # Check if script exists
    local script_path="$(dirname "$0")/rtsp_mic_server.py"
    if [[ ! -f "$script_path" ]]; then
        print_error "RTSP server script not found: $script_path"
        return 1
    fi
    
    # Quick test of the script
    if python3 "$script_path" --help &> /dev/null; then
        print_status "RTSP server script working"
    else
        print_error "RTSP server script has issues"
        return 1
    fi
    
    # List available devices
    print_info "Available audio devices:"
    python3 "$script_path" --list-devices
}

# Create service file
setup_service() {
    local create_service="n"
    echo
    read -p "Create systemd service for automatic startup? [y/N]: " create_service
    
    if [[ "$create_service" =~ ^[Yy]$ ]]; then
        local service_file="/etc/systemd/system/rtsp-mic.service"
        local script_dir="$(cd "$(dirname "$0")" && pwd)"
        local twin_dir="$(dirname "$script_dir")"
        
        print_info "Creating systemd service..."
        
        # Create service file with correct paths
        sudo tee "$service_file" > /dev/null << EOF
[Unit]
Description=Twin RTSP Microphone Server
After=sound.target network.target
Wants=sound.target

[Service]
Type=simple
User=$USER
Group=audio
WorkingDirectory=$twin_dir
Environment=PULSE_RUNTIME_PATH=/run/user/$(id -u)/pulse
ExecStart=/usr/bin/python3 $script_dir/rtsp_mic_server.py --port 8554 --device default
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=rtsp-mic

# Security settings
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths=/run/user/$(id -u)

[Install]
WantedBy=multi-user.target
EOF
        
        # Add user to audio group
        sudo usermod -a -G audio "$USER" || print_warning "Could not add user to audio group"
        
        # Reload systemd
        sudo systemctl daemon-reload
        
        print_status "Service created: $service_file"
        print_info "To enable: sudo systemctl enable rtsp-mic"
        print_info "To start: sudo systemctl start rtsp-mic"
        print_info "To check status: sudo systemctl status rtsp-mic"
    fi
}

# Configure firewall
setup_firewall() {
    local setup_fw="n"
    echo
    read -p "Configure firewall to allow RTSP traffic? [y/N]: " setup_fw
    
    if [[ "$setup_fw" =~ ^[Yy]$ ]]; then
        print_info "Configuring firewall..."
        
        # Try different firewall tools
        if command -v ufw &> /dev/null; then
            sudo ufw allow 8554/tcp
            print_status "UFW rule added for port 8554"
        elif command -v firewall-cmd &> /dev/null; then
            sudo firewall-cmd --permanent --add-port=8554/tcp
            sudo firewall-cmd --reload
            print_status "Firewalld rule added for port 8554"
        else
            print_warning "No supported firewall tool found"
            print_info "Manually allow port 8554/tcp in your firewall"
        fi
    fi
}

# Main setup function
main() {
    echo "This script will:"
    echo "1. Check system compatibility"
    echo "2. Install required packages"
    echo "3. Test audio system"
    echo "4. Test RTSP server"
    echo "5. Optionally create systemd service"
    echo "6. Optionally configure firewall"
    echo
    
    read -p "Continue? [Y/n]: " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Nn]$ ]]; then
        echo "Setup cancelled."
        exit 0
    fi
    
    # Step 1: System check
    check_system
    
    # Step 2: Package manager detection
    local pkg_manager=$(detect_package_manager)
    print_info "Detected package manager: $pkg_manager"
    
    # Step 3: Check/install dependencies
    if ! check_dependencies; then
        print_info "Installing missing dependencies..."
        install_packages "$pkg_manager"
        
        # Re-check after installation
        if ! check_dependencies; then
            print_error "Failed to install all dependencies"
            exit 1
        fi
    fi
    
    # Step 4: Test audio
    test_audio
    
    # Step 5: Test RTSP server
    test_rtsp_server
    
    # Step 6: Optional service setup
    setup_service
    
    # Step 7: Optional firewall setup
    setup_firewall
    
    echo
    print_status "Setup complete!"
    echo
    print_info "Next steps:"
    echo "1. Test the server: python3 scripts/rtsp_mic_server.py"
    echo "2. Connect Twin: python3 main.py --source rtsp://localhost:8554/audio"
    echo "3. For multi-room setup, see scripts/README.md"
    echo
    print_info "Troubleshooting:"
    echo "- Check logs: journalctl -u rtsp-mic -f (if using service)"
    echo "- Test audio: pactl list short sources"
    echo "- Test stream: ffplay rtsp://localhost:8554/audio"
}

# Run main function
main "$@" 