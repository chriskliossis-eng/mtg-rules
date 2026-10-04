#!/bin/bash
cd "$(dirname "$0")/.."
echo "Εξαγωγή περιόδου. Ημερομηνίες ΗΗ/ΜΜ/ΕΕΕΕ, π.χ. 01/09/2026. Κενό = χωρίς όριο."
read -p "Από ημερομηνία: " APO
read -p "Έως ημερομηνία: " EOS
ARGS=()
[ -n "$APO" ] && ARGS+=(--from "$APO")
[ -n "$EOS" ] && ARGS+=(--to "$EOS")
.venv/bin/fbwatch export --format all "${ARGS[@]}"
open data/exports 2>/dev/null
read -p "Πάτα Enter για κλείσιμο"
