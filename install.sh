#!/bin/bash
# Run this on the Raspberry Pi to set everything up.
# Usage: bash install.sh

set -e

echo "==> Updating system..."
sudo apt update -q
sudo apt install -y python3-pip bluetooth bluez python3-venv

echo "==> Creating virtual environment..."
python3 -m venv venv
source venv/bin/activate

echo "==> Installing Python dependencies..."
pip install -r requirements.txt

echo "==> Checking Bluetooth..."
sudo systemctl enable bluetooth
sudo systemctl start bluetooth
sudo hciconfig hci0 up 2>/dev/null || true

echo ""
echo "Done. Next steps:"
echo ""
echo "  1. Copy config:   cp config.json.example config.json"
echo "     Then edit config.json with your details."
echo ""
echo "  2. Find your scale MAC address:"
echo "     source venv/bin/activate && python3 scan.py"
echo ""
echo "  3. Test one reading:"
echo "     python3 listener.py"
echo ""
echo "  4. Install as a background service (runs forever):"
echo "     sudo cp scale.service /etc/systemd/system/"
echo "     sudo sed -i 's|/home/pi/scale-scrapper|$(pwd)|g' /etc/systemd/system/scale.service"
echo "     sudo systemctl daemon-reload"
echo "     sudo systemctl enable scale"
echo "     sudo systemctl start scale"
echo "     sudo journalctl -u scale -f   # watch logs"
