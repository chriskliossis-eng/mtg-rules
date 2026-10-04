#!/bin/bash
cd "$(dirname "$0")/.."
.venv/bin/fbwatch run
echo; echo "Τα screenshots είναι στον φάκελο data/screenshots"
read -p "Πάτα Enter για κλείσιμο"
