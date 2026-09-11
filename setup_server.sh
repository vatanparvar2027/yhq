#!/bin/bash
# ===============================================================
# CHIROQCHIMUZ Musiqa Botini VPS serverga avtomatik o'rnatish
# ===============================================================

set -e

echo "🚀 1. Server yangilanmoqda va zarur dasturlar o'rnatilmoqda..."
sudo apt-get update -y
sudo apt-get install -y python3 python3-pip python3-venv ffmpeg git curl

INSTALL_DIR="/opt/chiroqchimuz"
echo "📁 2. Loyiha papkasi tayyorlanmoqda: $INSTALL_DIR"
sudo mkdir -p "$INSTALL_DIR"
sudo chown -R $USER:$USER "$INSTALL_DIR"

# Agar fayllar joriy papkada bo'lsa nusxalaymiz
if [ -f "main.py" ]; then
    cp -r ./* "$INSTALL_DIR/"
    cp -r ./.[!.]* "$INSTALL_DIR/" 2>/dev/null || true
fi

cd "$INSTALL_DIR"

echo "🐍 3. Python virtual environment (venv) yaratilmoqda..."
python3 -m venv venv
source venv/bin/activate

echo "📦 4. Kutubxonalar o'rnatilmoqda..."
pip install --upgrade pip
pip install -r requirements.txt

echo "⚙️ 5. Systemd 24/7 xizmati (service) yaratilmoqda..."
SERVICE_FILE="/etc/systemd/system/chiroqchimuz.service"

sudo bash -c "cat > $SERVICE_FILE" <<EOL
[Unit]
Description=CHIROQCHIMUZ Telegram Music Bot
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$INSTALL_DIR
ExecStart=$INSTALL_DIR/venv/bin/python main.py
Restart=always
RestartSec=5
StandardOutput=syslog
StandardError=syslog
SyslogIdentifier=chiroqchimuz

[Install]
WantedBy=multi-user.target
EOL

echo "🔄 6. Xizmat ishga tushirilmoqda..."
sudo systemctl daemon-reload
sudo systemctl enable chiroqchimuz.service
sudo systemctl restart chiroqchimuz.service

echo ""
echo "==============================================================="
echo "✅ BOT SERVERDA MUVAFFAQIYATLI ISHGA TUSHIRILDI!"
echo "Bot 24/7 rejimida uzluksiz ishlaydi va server o'chib yonsa ham avtomatik yonadi."
echo ""
echo "📊 Holatini tekshirish: sudo systemctl status chiroqchimuz"
echo "📜 Loglarni ko'rish:    sudo journalctl -u chiroqchimuz -f"
echo "🔄 Qayta ishga tushirish: sudo systemctl restart chiroqchimuz"
echo "⏹ To'xtatish:          sudo systemctl stop chiroqchimuz"
echo "==============================================================="
