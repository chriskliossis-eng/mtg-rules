#!/bin/bash
cd "$(dirname "$0")/.."
if [ ! -x .venv/bin/python ]; then echo "Δεν έχει γίνει εγκατάσταση. Τρέξε πρώτα το 1_egkatastasi.command"; read -p "Enter"; exit 1; fi
.venv/bin/python -m fbwatch gui
