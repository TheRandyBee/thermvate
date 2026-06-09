#!/usr/bin/env bash
set -euo pipefail

# ═══════════════════════════════════════════════════════════════
# ThermVate — RPi Orchestrator Setup Script
# ═══════════════════════════════════════════════════════════════
#
# Installs and configures everything needed to run the ThermVate
# orchestrator on a Raspberry Pi 5 (or any Debian-based system).
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/TheRandyBee/thermvate/main/scripts/setup.sh | bash
#   # or locally:
#   sudo bash scripts/setup.sh
#
# What it does:
#   1. Installs system packages (Mosquitto, InfluxDB, Python, etc.)
#   2. Creates thermvate user and directory structure
#   3. Sets up Python venv with all dependencies
#   4. Configures Mosquitto MQTT broker for IoT sensors
#   5. Configures InfluxDB with thermvate database + retention
#   6. Creates systemd service for the orchestrator
#   7. Sets up log rotation
#   8. Optionally enables ESPHome for sensor firmware flashing
#
# ═══════════════════════════════════════════════════════════════

# ── Colors ────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

info()  { echo -e "${BLUE}[INFO]${NC} $*"; }
ok()    { echo -e "${GREEN}[OK]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
err()   { echo -e "${RED}[ERR]${NC} $*"; }

# ── Configuration ─────────────────────────────────────────────
# Edit these before running if your paths differ

THERMVATE_USER="${THERMVATE_USER:-thermvate}"
THERMVATE_HOME="/home/${THERMVATE_USER}"
THERMVATE_REPO="${THERMVATE_REPO:-https://github.com/TheRandyBee/thermvate.git}"
THERMVATE_BRANCH="${THERMVATE_BRANCH:-main}"
THERMVATE_CONFIG_DIR="${THERMVATE_CONFIG_DIR:-/etc/thermvate}"
THERMVATE_DATA_DIR="${THERMVATE_DATA_DIR:-/var/lib/thermvate}"
THERMVATE_LOG_DIR="${THERMVATE_LOG_DIR:-/var/log/thermvate}"

INFLUXDB_BUCKET="${INFLUXDB_BUCKET:-thermvate_data}"
INFLUXDB_RETENTION_DAYS="${INFLUXDB_RETENTION_DAYS:-90}"
MQTT_TOPIC_PREFIX="${MQTT_TOPIC_PREFIX:-thermvate}"

# Architecture detection
ARCH=$(uname -m)

# ── Pre-flight Checks ─────────────────────────────────────────

preflight() {
    info "Running pre-flight checks..."

    if [[ $EUID -ne 0 ]]; then
        err "This script must be run as root (sudo)."
        exit 1
    fi

    if [[ "$ARCH" != "aarch64" && "$ARCH" != "x86_64" ]]; then
        warn "Architecture '$ARCH' not tested. Proceeding anyway..."
    fi

    # Check we're on a Debian-based system
    if [ ! -f /etc/debian_version ]; then
        warn "Non-Debian system detected. Package installation may fail."
    fi

    ok "Pre-flight checks passed"
}

# ── System Packages ───────────────────────────────────────────

install_system_packages() {
    info "Installing system packages..."

    apt-get update -qq

    # Core
    apt-get install -y -qq \
        python3 \
        python3-pip \
        python3-venv \
        git \
        curl \
        wget \
        mosquitto \
        mosquitto-clients

    # InfluxDB — install from official repo
    if ! command -v influxd &>/dev/null; then
        info "Installing InfluxDB..."
        if [[ "$ARCH" == "aarch64" ]]; then
            wget -q https://dl.influxdata.com/influxdb/releases/influxdb2-2.7.11-arm64.deb
            dpkg -i influxdb2-2.7.11-arm64.deb
            rm influxdb2-2.7.11-arm64.deb
        else
            wget -q https://dl.influxdata.com/influxdb/releases/influxdb2-2.7.11-1-amd64.deb
            dpkg -i influxdb2-2.7.11-1-amd64.deb
            rm influxdb2-2.7.11-1-amd64.deb
        fi
    else
        ok "InfluxDB already installed"
    fi

    # Optional: esphome for sensor firmware compilation
    if command -v esphome &>/dev/null; then
        ok "ESPHome already installed"
    else
        warn "ESPHome not found. Install later with: pip install esphome"
    fi

    # Development tools (optional)
    apt-get install -y -qq \
        ufw \
        htop \
        iftop || true

    ok "System packages installed"
}

# ── User and Directories ──────────────────────────────────────

setup_user_and_dirs() {
    info "Creating thermvate user and directories..."

    if ! id -u "$THERMVATE_USER" &>/dev/null 2>&1; then
        useradd --system --create-home --shell /usr/sbin/nologin "$THERMVATE_USER"
        ok "Created user '$THERMVATE_USER'"
    else
        ok "User '$THERMVATE_USER' already exists"
    fi

    # Create data directories
    mkdir -p "$THERMVATE_CONFIG_DIR"
    mkdir -p "$THERMVATE_DATA_DIR"
    mkdir -p "$THERMVATE_LOG_DIR"
    mkdir -p "$THERMVATE_HOME/thermvate"

    chown -R "$THERMVATE_USER:$THERMVATE_USER" "$THERMVATE_HOME"
    chown -R "$THERMVATE_USER:$THERMVATE_USER" "$THERMVATE_DATA_DIR"
    chown -R "$THERMVATE_USER:$THERMVATE_USER" "$THERMVATE_LOG_DIR"

    ok "Directories created"
}

# ── Clone Repo ────────────────────────────────────────────────

clone_repo() {
    info "Cloning ThermVate repository..."

    if [ -d "$THERMVATE_HOME/thermvate/.git" ]; then
        warn "Repository already exists, pulling latest..."
        cd "$THERMVATE_HOME/thermvate"
        sudo -u "$THERMVATE_USER" git pull
    else
        sudo -u "$THERMVATE_USER" git clone \
            --branch "$THERMVATE_BRANCH" \
            "$THERMVATE_REPO" \
            "$THERMVATE_HOME/thermvate"
        ok "Repository cloned"
    fi

    # Copy example config if no config exists yet
    if [ ! -f "$THERMVATE_CONFIG_DIR/config.yaml" ]; then
        cp "$THERMVATE_HOME/thermvate/orchestrator/config.example.yaml" \
           "$THERMVATE_CONFIG_DIR/config.yaml"
        chown "$THERMVATE_USER:$THERMVATE_USER" \
           "$THERMVATE_CONFIG_DIR/config.yaml"
        warn "EDIT THIS FILE: $THERMVATE_CONFIG_DIR/config.yaml"
        warn "  Set your CWCVT IP, BACnet device instance, zones, etc."
    else
        ok "Config already exists at $THERMVATE_CONFIG_DIR/config.yaml"
    fi
}

# ── Python Virtual Environment ────────────────────────────────

setup_venv() {
    info "Setting up Python virtual environment..."

    VENV_DIR="$THERMVATE_HOME/venv"

    if [ -d "$VENV_DIR" ]; then
        warn "Virtual env already exists, updating..."
    else
        python3 -m venv "$VENV_DIR"
        ok "Virtual env created"
    fi

    # Upgrade pip
    "$VENV_DIR/bin/pip" install --quiet --upgrade pip

    # Install thermvate deps
    "$VENV_DIR/bin/pip" install --quiet \
        paho-mqtt>=2.1.0 \
        pyyaml>=6.0 \
        influxdb-client>=1.40.0 \
        influxdb>=5.3.0 \
        scikit-learn>=1.3.0 \
        numpy>=1.24.0 \
        pandas>=2.0.0 \
        prophet>=1.1.0 \
        BAC0>=21.12.0 \
        bacpypes>=0.18.0 \
        minimalmodbus>=2.1.0 \
        fastapi>=0.100.0 \
        uvicorn>=0.22.0 \
        pydantic>=2.0.0 \
        psutil>=5.9.0

    chown -R "$THERMVATE_USER:$THERMVATE_USER" "$VENV_DIR"

    ok "Python dependencies installed"
}

# ── Mosquitto Configuration ───────────────────────────────────

configure_mosquitto() {
    info "Configuring Mosquitto MQTT broker..."

    cat > /etc/mosquitto/conf.d/thermvate.conf << 'EOF'
# ThermVate MQTT Configuration

# Listen on all interfaces for sensor traffic
listener 1883 0.0.0.0
protocol mqtt

# Allow anonymous connections for local sensor network
allow_anonymous true

# Persistence for message reliability
persistence true
persistence_location /var/lib/mosquitto/
autosave_interval 1800

# Logging
log_type notice
log_type warning
log_type error
connection_messages true
log_timestamp true

# Maximum QoS
max_inflight_messages 20
max_queued_messages 1000

# Prevent MQTT bridge loops (not applicable but safe)
bridge_protocol false
EOF

    systemctl enable mosquitto
    systemctl restart mosquitto
    ok "Mosquitto configured and running"
}

# ── InfluxDB Configuration ────────────────────────────────────

configure_influxdb() {
    info "Configuring InfluxDB..."

    systemctl enable influxdb
    systemctl restart influxdb

    # Wait for InfluxDB to be ready
    sleep 3

    # Create bucket via InfluxDB v2 API (also creates org if needed)
    if ! influx bucket list --org thermvate 2>/dev/null | grep -q "$INFLUXDB_BUCKET"; then
        # InfluxDB setup (first-time)
        influx setup \
            --org thermvate \
            --bucket "$INFLUXDB_BUCKET" \
            --username thermvate \
            --password thermvate123 \
            --force 2>/dev/null || true

        # Configure retention
        influx bucket create \
            --name "$INFLUXDB_BUCKET" \
            --org thermvate \
            --retention "${INFLUXDB_RETENTION_DAYS}d" 2>/dev/null || true

        ok "InfluxDB bucket '$INFLUXDB_BUCKET' created"
    else
        ok "InfluxDB bucket '$INFLUXDB_BUCKET' already exists"
    fi

    # Show the operator token for config.yaml
    info "InfluxDB operator token (add to your config.yaml):"
    influx auth list --org thermvate 2>/dev/null | head -4 || true
}

# ── Systemd Service ──────────────────────────────────────────

setup_systemd_service() {
    info "Creating systemd service..."

    cat > /etc/systemd/system/thermvate.service << 'EOF'
[Unit]
Description=ThermVate AI HVAC Orchestrator
Documentation=https://github.com/TheRandyBee/thermvate
After=network-online.target mosquitto.service influxdb.service
Wants=network-online.target mosquitto.service influxdb.service

[Service]
Type=simple
User=thermvate
Group=thermvate

Environment=THERMVATE_CONFIG=/etc/thermvate/config.yaml
Environment=THERMVATE_DATA=/var/lib/thermvate
Environment=PYTHONUNBUFFERED=1

WorkingDirectory=/home/thermvate/thermvate
ExecStart=/home/thermvate/venv/bin/python -m orchestrator.src.main

Restart=always
RestartSec=10
StartLimitIntervalSec=300
StartLimitBurst=5

# Security hardening
NoNewPrivileges=true
ProtectSystem=strict
ReadWritePaths=/var/lib/thermvate /var/log/thermvate /etc/thermvate
PrivateTmp=true
ProtectHome=true
ProtectKernelTunables=true
ProtectControlGroups=true

# Resource limits
LimitNOFILE=65536
CPUQuota=50%
MemoryMax=512M

StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

    systemctl daemon-reload
    systemctl enable thermvate.service
    ok "systemd service created (thermvate.service)"
}

# ── Log Rotation ──────────────────────────────────────────────

setup_logrotate() {
    info "Configuring log rotation..."

    cat > /etc/logrotate.d/thermvate << 'EOF'
/var/log/thermvate/*.log {
    daily
    rotate 30
    compress
    delaycompress
    missingok
    notifempty
    copytruncate
}
EOF

    ok "Log rotation configured"
}

# ── Firewall ──────────────────────────────────────────────────

configure_firewall() {
    info "Configuring firewall..."

    if command -v ufw &>/dev/null; then
        ufw allow 1883/tcp comment "MQTT - ThermVate sensors"
        ufw allow 8086/tcp comment "InfluxDB - ThermVate"
        # BACnet/IP uses UDP 47808 — only needed locally
        # ufw allow 47808/udp comment "BACnet/IP"
        ok "Firewall rules added"
    else
        warn "ufw not installed, skip firewall configuration"
    fi
}

# ── Validation ────────────────────────────────────────────────

validate_installation() {
    info "Validating installation..."

    local errors=0

    # Check services
    for svc in mosquitto influxdb; do
        if systemctl is-active --quiet "$svc"; then
            echo "  ✅ $svc running"
        else
            echo "  ❌ $svc NOT running"
            errors=$((errors + 1))
        fi
    done

    # Check thermvate service file
    if [ -f /etc/systemd/system/thermvate.service ]; then
        echo "  ✅ thermvate.service installed"
    else
        echo "  ❌ thermvate.service missing"
        errors=$((errors + 1))
    fi

    # Check venv
    if [ -f "$THERMVATE_HOME/venv/bin/python" ]; then
        echo "  ✅ Python venv exists"
    else
        echo "  ❌ Python venv missing"
        errors=$((errors + 1))
    fi

    # Check config
    if [ -f "$THERMVATE_CONFIG_DIR/config.yaml" ]; then
        echo "  ✅ Config file exists"
    else
        echo "  ⚠️  Config file missing — create from example"
    fi

    # Test import
    if sudo -u "$THERMVATE_USER" "$THERMVATE_HOME/venv/bin/python" \
        -c "import sys; sys.path.insert(0,'$THERMVATE_HOME/thermvate'); \
            from orchestrator.src.safety import SafetyEnforcer; \
            print('  ✅ Python imports OK')" 2>/dev/null; then
        :
    else
        echo "  ❌ Python import test failed"
        errors=$((errors + 1))
    fi

    if [ "$errors" -eq 0 ]; then
        ok "All checks passed! 🎉"
    else
        warn "$errors check(s) failed — review above"
    fi
}

# ── Summary ───────────────────────────────────────────────────

print_summary() {
    echo ""
    echo "╔══════════════════════════════════════════════════════╗"
    echo "║          ThermVate Installation Complete            ║"
    echo "╚══════════════════════════════════════════════════════╝"
    echo ""
    echo "  Config:      $THERMVATE_CONFIG_DIR/config.yaml"
    echo "  Data:        $THERMVATE_DATA_DIR"
    echo "  Logs:        $THERMVATE_LOG_DIR"
    echo "  Repo:        $THERMVATE_HOME/thermvate"
    echo "  Venv:        $THERMVATE_HOME/venv"
    echo "  Service:     thermvate.service"
    echo ""
    echo "  ── Next Steps ──"
    echo "  1. EDIT $THERMVATE_CONFIG_DIR/config.yaml"
    echo "     with your CWCVT IP, BACnet device, zones"
    echo ""
    echo "  2. Start the orchestrator:"
    echo "     sudo systemctl start thermvate"
    echo "     sudo journalctl -u thermvate -f"
    echo ""
    echo "  3. Flash ESP32 sensors:"
    echo "     cd $THERMVATE_HOME/thermvate"
    echo "     source $THERMVATE_HOME/venv/bin/activate"
    echo "     pip install esphome"
    echo "     esphome run firmware/esp32-sensor.yaml"
    echo ""
    echo "  4. Check MQTT sensor data:"
    echo "     mosquitto_sub -t 'thermvate/#' -v"
    echo ""
    echo "  5. Apply for grant:"
    echo "     https://aigrant.org"
    echo "     (proposal in grants/ai-grant-proposal.md)"
    echo ""
}

# ═══════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════

main() {
    echo ""
    echo "╔══════════════════════════════════════════════════════╗"
    echo "║      ThermVate RPi Orchestrator Setup v0.1          ║"
    echo "╚══════════════════════════════════════════════════════╝"
    echo ""

    preflight
    install_system_packages
    setup_user_and_dirs
    clone_repo
    setup_venv
    configure_mosquitto
    configure_influxdb
    setup_systemd_service
    setup_logrotate
    configure_firewall
    validate_installation
    print_summary
}

main "$@"
