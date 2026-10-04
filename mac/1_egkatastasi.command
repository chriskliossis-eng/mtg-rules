#!/bin/bash
cd "$(dirname "$0")/.."
echo "============================================"
echo "  fbwatch - Εγκατάσταση (μία φορά)"
echo "============================================"
if ! command -v python3 >/dev/null 2>&1; then
  echo "ΔΕΝ βρέθηκε η Python. Κατέβασέ την από https://www.python.org/downloads/ και ξανατρέξε αυτό το αρχείο."
  read -p "Πάτα Enter για έξοδο"; exit 1
fi
echo "[1/4] Δημιουργία περιβάλλοντος Python..."
[ -d .venv ] || python3 -m venv .venv || { read -p "Σφάλμα. Enter για έξοδο"; exit 1; }
echo "[2/4] Εγκατάσταση του fbwatch..."
.venv/bin/python -m pip install --quiet --upgrade pip
.venv/bin/python -m pip install --quiet -e . tzdata || { echo "Σφάλμα εγκατάστασης. Ελέγξε το internet."; read -p "Enter για έξοδο"; exit 1; }
echo "[3/4] Κατέβασμα του browser (Chromium, ~150MB)..."
.venv/bin/python -m playwright install chromium || { read -p "Σφάλμα. Enter για έξοδο"; exit 1; }
echo "[4/4] Ρυθμίσεις..."
[ -f config.yaml ] || cp config.example.yaml config.yaml
echo
echo "Η εγκατάσταση ολοκληρώθηκε. Ανοίγει το πρόγραμμα."
echo "Από εδώ και πέρα, για να το ανοίγεις: διπλό κλικ στο 0_programma.command"
.venv/bin/python -m fbwatch gui
