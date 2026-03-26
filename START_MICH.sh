#!/bin/bash
# Linux-Starter fuer TUXPLAYER Backup System
# Einfach doppelklicken (oder: bash START_MICH.sh)

cd "$(dirname "$0")"

python3 tuxplayer_backup_gui.py 2>/dev/null && exit 0
python  tuxplayer_backup_gui.py 2>/dev/null && exit 0

echo ""
echo "============================================================"
echo " Python wurde nicht gefunden!"
echo "============================================================"
echo ""
echo " Bitte installiere Python (kostenlos):"
echo ""
echo " Ubuntu/Debian:  sudo apt install python3"
echo " Fedora:         sudo dnf install python3"
echo " Arch:           sudo pacman -S python"
echo ""
echo " Danach diese Datei nochmal starten."
echo "============================================================"
read -p "Druecke Enter zum Beenden..."
