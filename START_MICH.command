#!/bin/bash
# Mac-Starter fuer TUXPLAYER Backup System
# Einfach doppelklicken!

cd "$(dirname "$0")"

python3 tuxplayer_backup_gui.py 2>/dev/null && exit 0
python  tuxplayer_backup_gui.py 2>/dev/null && exit 0

osascript -e '
display dialog "Python wurde nicht gefunden!\n\nBitte installiere Python (kostenlos):\n\n1. Gehe zu: https://www.python.org/downloads/\n2. Lade Python herunter und installiere es\n3. Danach diese Datei nochmal doppelklicken" \
buttons {"OK"} default button "OK" with icon caution \
with title "TUXPLAYER – Python benoetigt"
' 2>/dev/null || echo "Python nicht gefunden. Bitte von https://python.org installieren."
