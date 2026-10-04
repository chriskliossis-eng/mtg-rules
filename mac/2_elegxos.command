#!/bin/bash
cd "$(dirname "$0")/.."
echo "fbwatch - Έλεγχος πρόσβασης (χωρίς αποθήκευση). Θα ανοίξει browser, μην τον αγγίξεις."
.venv/bin/fbwatch check --headed --dump
echo
echo "Αν στη Σύνοψη βλέπεις 'ok' με αριθμό posts, τρέξε το 3_syllogi.command"
echo "Αλλιώς στείλε τα αρχεία από τον φάκελο data/debug"
read -p "Πάτα Enter για κλείσιμο"
