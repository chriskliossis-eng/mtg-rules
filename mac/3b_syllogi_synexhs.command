#!/bin/bash
cd "$(dirname "$0")/.."
echo "Συνεχής συλλογή κάθε 2 ώρες. Άφησε το παράθυρο ανοιχτό. Για διακοπή: Ctrl+C ή κλείσε το παράθυρο."
.venv/bin/fbwatch run --loop --every 2h
