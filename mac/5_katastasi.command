#!/bin/bash
cd "$(dirname "$0")/.."
.venv/bin/fbwatch status; echo; .venv/bin/fbwatch list
read -p "Πάτα Enter για κλείσιμο"
