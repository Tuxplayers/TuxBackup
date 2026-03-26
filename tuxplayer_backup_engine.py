#!/usr/bin/env python3
# ==============================================================================
# TuxBackup — Backup-Engine v5.0.0
# ==============================================================================
# AUTOR         : Heiko Schaefer (TUXPLAYER)
# VERSION       : 5.0.0
# BESCHREIBUNG  : Backup-Engine fuer TuxBackup.
#                 Sichert das Home-Verzeichnis als komprimiertes tar.gz-Archiv
#                 mit SHA256-Pruefsumme (on-the-fly, kein 2. Durchlauf).
#                 Zielverzeichnis wird per --target oder tux_config.json gesetzt.
# ABHAENGIGK.   : tar, systemd-inhibit (optional, nur Linux)
# LIZENZ        : MIT
# WEBSITE       : https://tuxhs.de
# GITHUB        : https://github.com/Tuxplayers/TuxBackup
# PATREON       : https://www.patreon.com/c/u19664883
# ==============================================================================

import os
import glob
import subprocess
import sys
import hashlib
import json
import argparse
from datetime import datetime

VERSION   = "5.0.0"
MAX_KEEP  = 3
MIN_FREE_GB  = 10
MIN_BACKUP_MB = 100

# ── Konfiguration laden ────────────────────────────────────────────────────────
def load_config() -> dict:
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tux_config.json")
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

# ── Globale Pfade (werden in main() gesetzt) ──────────────────────────────────
BACKUP_SOURCE     = ""
BACKUP_TARGET_DIR = ""
LOGFILE           = ""
INVENTORY_FILE    = ""
RESTORE_SCRIPT    = ""
FILENAME          = ""
_log_lines: list  = []

TAR_EXCLUDE_COMMON = [
    "--exclude=.cache",
    "--exclude=.local/share/Trash",
    "--exclude=.mozilla/firefox/*/storage",
    "--exclude=Steam",
    "--exclude=snap",
    "--exclude=.config/google-chrome/*/Cache",
    "--exclude=.config/google-chrome/*/Code Cache",
    "--exclude=.config/chromium/*/Cache",
    "--exclude=.config/chromium/*/Code Cache",
    "--exclude=.config/BraveSoftware/*/Cache",
    "--exclude=.config/Microsoft/Edge/*/Cache",
    "--exclude=.zoom/data/cefcache",
    "--exclude=.config/discord/Cache",
    "--exclude=.config/discord/Code Cache",
    "--exclude=.config/TikTok",
    "--exclude=Downloads",
    "--exclude=VirtualBox VMs",
]

# ── Logging ────────────────────────────────────────────────────────────────────
def log(msg: str, level: str = "INFO"):
    ts   = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] [{level}] {msg}"
    print(line, flush=True)
    _log_lines.append(line)

def flush_log():
    if not LOGFILE:
        return
    try:
        with open(LOGFILE, "a", encoding="utf-8") as f:
            for line in _log_lines:
                f.write(line + "\n")
            f.write("\n")
    except Exception as e:
        print(f"[WARN] Log konnte nicht geschrieben werden: {e}")

# ── Pruefungen ────────────────────────────────────────────────────────────────
def check_target():
    if not os.path.isdir(BACKUP_TARGET_DIR):
        try:
            os.makedirs(BACKUP_TARGET_DIR, exist_ok=True)
        except Exception as e:
            log(f"Zielverzeichnis nicht erreichbar: {BACKUP_TARGET_DIR} ({e})", "ERROR")
            sys.exit(1)
    log(f"Ziel OK: {BACKUP_TARGET_DIR}")

def check_free_space():
    stat    = os.statvfs(BACKUP_TARGET_DIR)
    free_gb = (stat.f_bavail * stat.f_frsize) / (1024 ** 3)
    log(f"Freier Speicher: {free_gb:.1f} GB (Minimum: {MIN_FREE_GB} GB)")
    if free_gb < MIN_FREE_GB:
        log(f"Nicht genug Speicherplatz! Benoetigt: {MIN_FREE_GB} GB", "ERROR")
        sys.exit(1)

# ── Hilfsfunktionen ───────────────────────────────────────────────────────────
def human_size(b: int) -> str:
    for u in ["B", "KB", "MB", "GB", "TB"]:
        if b < 1024.0:
            return f"{b:.1f} {u}"
        b /= 1024.0
    return f"{b:.1f} PB"

def check_inhibit() -> bool:
    return subprocess.run(["which", "systemd-inhibit"],
                          capture_output=True).returncode == 0

def start_inhibit():
    if not check_inhibit():
        log("systemd-inhibit nicht verfuegbar (optional).", "WARN")
        return None
    try:
        proc = subprocess.Popen([
            "systemd-inhibit", "--what=sleep:idle",
            "--who=TUXPLAYER-BACKUP", "--why=Backup laeuft",
            "--mode=block", "sleep", "infinity"
        ])
        log(f"Suspend-Schutz aktiv (PID {proc.pid})")
        return proc
    except Exception as e:
        log(f"Suspend-Schutz Fehler: {e}", "WARN")
        return None

def stop_inhibit(proc):
    if proc and proc.poll() is None:
        proc.terminate()
        proc.wait()
        log("Suspend-Schutz aufgehoben.")

def get_tar_excludes() -> list:
    home = os.path.expanduser("~")
    extra = [f"--exclude={home}/Downloads"]
    return TAR_EXCLUDE_COMMON + extra

def create_restore_script():
    script = (
        '#!/bin/bash\n'
        '# TUXPLAYER Restore Script\n'
        'SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"\n'
        'mapfile -t BACKUPS < <(ls -t "$SCRIPT_DIR"/TUX_FULL_BACKUP_*.tar.gz 2>/dev/null)\n'
        'if [ ${#BACKUPS[@]} -eq 0 ]; then echo "FEHLER: Keine Backups gefunden!"; exit 1; fi\n'
        'echo "Verfuegbare Backups:"\n'
        'for i in "${!BACKUPS[@]}"; do\n'
        '    SIZE=$(du -sh "${BACKUPS[$i]}" | cut -f1)\n'
        '    echo "  [$i] $(basename "${BACKUPS[$i]}") | $SIZE"\n'
        'done\n'
        'read -rp "Welches Backup wiederherstellen? [Nummer]: " CHOICE\n'
        'SELECTED="${BACKUPS[$CHOICE]}"\n'
        'read -rp "Ziel-Verzeichnis (z.B. /tmp/restore): " TARGET\n'
        'mkdir -p "$TARGET"\n'
        'echo "Stelle wieder her: $(basename "$SELECTED")"\n'
        'tar -xzf "$SELECTED" -C "$TARGET" --strip-components=2\n'
        'echo "Fertig! Dateien unter: $TARGET"\n'
    )
    with open(RESTORE_SCRIPT, "w", encoding="utf-8") as f:
        f.write(script)
    os.chmod(RESTORE_SCRIPT, 0o755)
    log("Restore-Script geschrieben.")

def copy_gui_files():
    import shutil
    script_dir = os.path.dirname(os.path.abspath(__file__))
    for filename in ["tuxplayer_backup_gui.py", "START_MICH.bat",
                     "START_MICH.command", "START_MICH.sh"]:
        src = os.path.join(script_dir, filename)
        dst = os.path.join(BACKUP_TARGET_DIR, filename)
        if os.path.exists(src):
            shutil.copy2(src, dst)
            log(f"GUI-Datei kopiert: {filename}")
        else:
            log(f"GUI-Datei nicht gefunden (uebersprungen): {filename}", "WARN")

def update_inventory():
    pattern = os.path.join(BACKUP_TARGET_DIR, "TUX_FULL_BACKUP_*.tar.gz")
    backups = sorted(glob.glob(pattern), key=os.path.getmtime, reverse=True)
    with open(INVENTORY_FILE, "w", encoding="utf-8") as f:
        f.write("=" * 65 + "\n")
        f.write("  BACKUP-INVENTAR - TuxBackup SYSTEM\n")
        f.write(f"  Stand: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}\n")
        f.write("=" * 65 + "\n\n")
        for bp in backups:
            size  = human_size(os.path.getsize(bp))
            mtime = datetime.fromtimestamp(os.path.getmtime(bp)).strftime("%d.%m.%Y %H:%M")
            chk   = "OK SHA256" if os.path.exists(bp + ".sha256") else "- kein SHA256"
            f.write(f"  {os.path.basename(bp):<45} {size:>8}  {mtime}  [{chk}]\n")
        f.write(f"\n  Gesamt: {len(backups)} Backup(s) (Maximum: {MAX_KEEP})\n")
        f.write("=" * 65 + "\n")
    log(f"Inventar aktualisiert ({len(backups)} Eintraege).")

def cleanup():
    pattern = os.path.join(BACKUP_TARGET_DIR, "TUX_FULL_BACKUP_*.tar.gz")
    backups = sorted(glob.glob(pattern), key=os.path.getmtime, reverse=True)
    if len(backups) > MAX_KEEP:
        for old in backups[MAX_KEEP:]:
            for path in [old, old + ".sha256"]:
                if os.path.exists(path):
                    try:
                        os.remove(path)
                        log(f"Altes Backup entfernt: {os.path.basename(path)}")
                    except Exception as e:
                        log(f"Loeschen fehlgeschlagen: {e}", "WARN")
    else:
        log(f"Platzmanagement: {len(backups)}/{MAX_KEEP} Backups. OK.")

# ── Dry-Run ───────────────────────────────────────────────────────────────────
def run_dry_run():
    log("=" * 55)
    log(f"TuxBackup v{VERSION} - DRY-RUN (Simulation)")
    log("HINWEIS: Es wird NICHTS geschrieben. Nur Test!")
    log("=" * 55)
    log(f"Quelle: {BACKUP_SOURCE}")
    log("Starte tar-Simulation...")

    cmd      = ["tar"] + get_tar_excludes() + ["-cz", BACKUP_SOURCE]
    warnings = 0
    counted  = 0
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        for chunk in iter(lambda: proc.stdout.read(4 * 1024 * 1024), b""):
            counted += len(chunk)
        _, stderr_out = proc.communicate()
        rc = proc.returncode

        for line in stderr_out.decode(errors="replace").splitlines():
            if line.strip():
                log(f"tar: {line.strip()}", "WARN")
                warnings += 1

        if rc == 0:
            log("tar: Simulation abgeschlossen.")
        elif rc == 1:
            log("tar: Einige Dateien haben sich geaendert (Exit 1) - Warnung.", "WARN")
            warnings += 1
        else:
            log(f"tar fehlgeschlagen (Exit-Code {rc})", "ERROR")
            log("DRY-RUN FEHLGESCHLAGEN")
            sys.exit(1)
    except Exception as e:
        log(f"Fehler: {e}", "ERROR")
        sys.exit(1)

    log("=" * 55)
    log("DRY-RUN ERGEBNIS:")
    log(f"  Simulierte Archivgroesse : {human_size(counted)}")
    log(f"  tar-Warnungen            : {warnings}")
    log(f"  Echtes Backup moeglich   : {'JA' if rc <= 1 else 'NEIN'}")
    log("  (Nichts wurde geschrieben)")
    log("=" * 55)

# ── Echtes Backup ─────────────────────────────────────────────────────────────
def run_backup():
    os.makedirs(BACKUP_TARGET_DIR, exist_ok=True)

    log("=" * 55)
    log(f"TuxBackup v{VERSION} - START")
    log("=" * 55)

    check_target()
    check_free_space()

    inhibit_proc = start_inhibit()
    full_path    = os.path.join(BACKUP_TARGET_DIR, FILENAME)
    log(f"Ziel: {FILENAME}")
    log(f"Quelle: {BACKUP_SOURCE}")
    log("Sicherung laeuft... (kann 1-2 Stunden dauern)")

    cmd = ["tar"] + get_tar_excludes() + ["-cz", BACKUP_SOURCE]
    try:
        tar_proc = subprocess.Popen(cmd, stdout=subprocess.PIPE)
        h       = hashlib.sha256()
        written = 0
        with open(full_path, "wb") as out_f:
            for chunk in iter(lambda: tar_proc.stdout.read(4 * 1024 * 1024), b""):
                out_f.write(chunk)
                h.update(chunk)
                written += len(chunk)
        tar_proc.wait()
        rc = tar_proc.returncode
        if rc == 0:
            log("tar: Backup erfolgreich abgeschlossen.")
        elif rc == 1:
            log("tar: Einige Dateien haben sich geaendert - wird als Warnung behandelt.", "WARN")
            log("tar: Archiv ist trotzdem verwendbar.", "WARN")
        else:
            log(f"tar fehlgeschlagen (Exit-Code {rc})", "ERROR")
            stop_inhibit(inhibit_proc)
            flush_log()
            sys.exit(1)
    except Exception as e:
        log(f"Fehler: {e}", "ERROR")
        stop_inhibit(inhibit_proc)
        flush_log()
        sys.exit(1)

    if not os.path.exists(full_path):
        log("Archiv-Datei nicht erstellt!", "ERROR")
        stop_inhibit(inhibit_proc)
        flush_log()
        sys.exit(1)

    size_bytes = os.path.getsize(full_path)
    if size_bytes < MIN_BACKUP_MB * 1024 * 1024:
        log(f"Archiv zu klein ({human_size(size_bytes)}) - fehlerhaft!", "ERROR")
        stop_inhibit(inhibit_proc)
        flush_log()
        sys.exit(1)

    log(f"Archiv erstellt: {human_size(size_bytes)}")

    checksum      = h.hexdigest()
    checksum_file = full_path + ".sha256"
    with open(checksum_file, "w") as f:
        f.write(f"{checksum}  {FILENAME}\n")
    log(f"SHA256: {checksum[:24]}...  OK (on-the-fly berechnet)")

    create_restore_script()
    copy_gui_files()
    cleanup()
    update_inventory()
    stop_inhibit(inhibit_proc)

    log("=" * 55)
    log(f"TuxBackup v{VERSION} ERFOLGREICH ABGESCHLOSSEN")
    log("=" * 55)
    flush_log()

# ── Einstiegspunkt ─────────────────────────────────────────────────────────────
def main():
    global BACKUP_SOURCE, BACKUP_TARGET_DIR, LOGFILE, INVENTORY_FILE
    global RESTORE_SCRIPT, FILENAME

    parser = argparse.ArgumentParser(
        description=f"TUXPLAYER Backup Engine v{VERSION}"
    )
    parser.add_argument("--target", help="Backup-Zielverzeichnis")
    parser.add_argument("--source", help="Zu sicherndes Verzeichnis (Standard: Home)")
    parser.add_argument("--dry-run", "--dry", dest="dry", action="store_true",
                        help="Simulation — nichts wird geschrieben")
    args = parser.parse_args()

    config = load_config()

    BACKUP_TARGET_DIR = args.target or config.get("backup_target", "")
    BACKUP_SOURCE     = args.source or config.get("backup_source",
                                                   os.path.expanduser("~"))

    if not BACKUP_TARGET_DIR:
        print("[ERROR] Kein Backup-Ziel konfiguriert.")
        print("        Bitte in der GUI unter 'Backup-Steuerung' ein Ziel auswaehlen,")
        print("        oder --target /pfad/zum/ziel angeben.")
        sys.exit(1)

    FILENAME       = f"TUX_FULL_BACKUP_{datetime.now().strftime('%Y%m%d_%H%M%S')}.tar.gz"
    LOGFILE        = os.path.join(BACKUP_TARGET_DIR, "backup_log.txt")
    INVENTORY_FILE = os.path.join(BACKUP_TARGET_DIR, "BACKUPS.txt")
    RESTORE_SCRIPT = os.path.join(BACKUP_TARGET_DIR, "tuxrestore.sh")

    if args.dry:
        run_dry_run()
    else:
        run_backup()

if __name__ == "__main__":
    main()
