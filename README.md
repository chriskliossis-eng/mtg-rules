# fbwatch

Εργαλείο γραμμής εντολών που συλλέγει **δημόσια posts από Facebook Pages χωρίς login**, κρατά
**screenshot κάθε post** μαζί με κείμενο, ημερομηνία, permalink και hash, και εξάγει τα αποτελέσματα
για όποια περίοδο επιλέξεις σε CSV, JSON, HTML και PDF.

Χρησιμοποιεί τα επίσημα embed plugins του Facebook (Page Plugin και Post Embed), που αποδίδουν
δημόσιο περιεχόμενο Pages χωρίς σύνδεση, μέσα από έναν αυτοματοποιημένο Chromium (Playwright).

## Χρήση χωρίς γνώσεις προγραμματισμού

Στους φακέλους `windows/` και `mac/` υπάρχουν αρχεία που τρέχουν με διπλό κλικ, με τη σειρά που
είναι αριθμημένα:

| Αρχείο | Τι κάνει |
|---|---|
| `1_egkatastasi` | Εγκατάσταση, μία φορά. Στο τέλος ανοίγει τις ρυθμίσεις για να βάλεις τις σελίδες. |
| `2_elegxos` | Δοκιμάζει αν το Facebook δίνει τα posts. Δεν αποθηκεύει τίποτα. |
| `3_syllogi` | Μαζεύει τα νέα posts και βγάζει screenshots. Τρέξε το όσο συχνά θέλεις. |
| `3b_syllogi_synexhs` | Το ίδιο, αλλά συνεχώς κάθε 2 ώρες όσο μένει ανοιχτό το παράθυρο. |
| `4_exagogi` | Ρωτάει από/έως ημερομηνία και φτιάχνει CSV, JSON, HTML και PDF. |
| `5_katastasi` | Δείχνει πόσα posts έχουν μαζευτεί ανά σελίδα. |

Προϋπόθεση: εγκατεστημένη Python από το https://www.python.org/downloads/ (στα Windows τσέκαρε
το κουτάκι "Add python.exe to PATH" στην πρώτη οθόνη της εγκατάστασης).

## Τι κάνει και τι όχι

| Λειτουργία | Χωρίς login |
|---|---|
| Timeline δημόσιας **Page** (ΜΜΕ, οργανισμοί, δημόσια πρόσωπα με Page) | Ναι, τα πρόσφατα posts |
| Μεμονωμένο δημόσιο post από το URL του | Ναι, συνήθως |
| Timeline **προσωπικού προφίλ** | Όχι, το Facebook ζητά σύνδεση |
| Αναδρομική συλλογή πολλών μηνών πίσω | Περιορισμένα, μόνο όσο φτάνει το plugin |
| Σχόλια, πλήρεις αριθμοί reactions | Όχι |

Η λογική είναι **παρακολούθηση από εδώ και πέρα**: τρέχεις το εργαλείο τακτικά (π.χ. κάθε 2 ώρες),
κάθε νέο post αποθηκεύεται μία φορά με screenshot, και η "περίοδος" που ζητάς στην εξαγωγή
είναι φίλτρο πάνω στο αρχείο που έχει συγκεντρωθεί.

## Εγκατάσταση

Χρειάζεται Python 3.10 ή νεότερο.

```bash
git clone https://github.com/chriskliossis-eng/mtg-rules.git fbwatch
cd fbwatch
python -m venv .venv
# Windows:  .venv\Scripts\activate
# macOS/Linux:  source .venv/bin/activate
pip install -e .
playwright install chromium
```

## Πρώτη δοκιμή (5 λεπτά)

1. Δημιούργησε config και βάλε τις Pages που θέλεις:

   ```bash
   fbwatch init
   ```

   Άνοιξε το `config.yaml` και άλλαξε την ενότητα `sources`:

   ```yaml
   sources:
     - id: ertnews
       kind: page
       url: https://www.facebook.com/ertnews
       label: ΕΡΤ News
   ```

2. Έλεγξε ότι το Facebook δίνει το περιεχόμενο, με ορατό παράθυρο και χωρίς αποθήκευση:

   ```bash
   fbwatch check --headed --dump
   ```

   Στη σύνοψη θέλεις `ok` με αριθμό posts. Αν δεις `login_wall`, `unavailable` ή `empty`,
   δες την ενότητα *Αντιμετώπιση προβλημάτων* πιο κάτω. Το `--dump` αποθηκεύει στο
   `data/debug/` το HTML και ένα πλήρες screenshot της σελίδας, χρήσιμα για διάγνωση.

3. Πρώτη συλλογή:

   ```bash
   fbwatch run
   ```

4. Δες τι μαζεύτηκε και εξήγαγε μια περίοδο:

   ```bash
   fbwatch list
   fbwatch export --from 2026-09-01 --to 2026-09-30 --format all
   ```

## Εντολές

| Εντολή | Τι κάνει |
|---|---|
| `fbwatch init` | Δημιουργεί `config.yaml` από το παράδειγμα |
| `fbwatch check [--headed] [--dump] [-s ID]` | Δοκιμή πρόσβασης χωρίς αποθήκευση |
| `fbwatch run [-s ID] [--since YYYY-MM-DD]` | Συλλογή νέων posts και screenshots |
| `fbwatch run --loop --every 2h` | Συνεχής λειτουργία με επανάληψη |
| `fbwatch capture URL [URL ...]` | Λήψη συγκεκριμένων posts από τα URL τους |
| `fbwatch list [--from] [--to] [-s ID]` | Λίστα αποθηκευμένων posts |
| `fbwatch export [--from] [--to] [-s ID] [-f csv/json/html/pdf/all] [-o DIR]` | Εξαγωγή |
| `fbwatch archive [--limit N]` | Snapshot στο archive.org για posts που δεν έχουν |
| `fbwatch status` | Πλήθη ανά πηγή και πρόσφατες εκτελέσεις |

Ημερομηνίες γίνονται δεκτές ως `YYYY-MM-DD` ή `DD/MM/YYYY`. Το φίλτρο εφαρμόζεται στην
ημερομηνία του post. Με `--date-field first_seen` φιλτράρεις με βάση το πότε το είδε το εργαλείο,
και με `--exclude-undated` παραλείπονται posts χωρίς αναγνωρισμένη ημερομηνία.

Η επιλογή `-c άλλο.yaml` σε κάθε εντολή επιτρέπει πολλά ανεξάρτητα config.

## Τι αποθηκεύεται

```
data/
  fbwatch.sqlite3            βάση: posts, ιστορικό λήψεων, εκτελέσεις
  screenshots/<πηγή>/<post_id>__<ώρα λήψης>.png
  html/<πηγή>/<post_id>__<ώρα λήψης>.html     το HTML του post με επικεφαλίδα λήψης
  exports/                   CSV, JSON, HTML, PDF
  debug/                     μόνο με check --dump
```

Για κάθε post κρατούνται: σταθερό αναγνωριστικό, permalink χωρίς tracking παραμέτρους, συντάκτης,
κείμενο, ημερομηνία post όπως την εμφάνισε το Facebook και όπως αναλύθηκε, ώρα πρώτης και
τελευταίας θέασης, διαδρομή screenshot, SHA-256 του screenshot, και προαιρετικά URL snapshot
στο archive.org.

**Αποδεικτική χρήση.** Ένα απλό screenshot αμφισβητείται εύκολα. Ο συνδυασμός screenshot,
HTML, ώρας λήψης, hash και ανεξάρτητου snapshot στο archive.org (`archive.enabled: true` στο config
ή `fbwatch archive`) είναι πολύ πιο ισχυρός. Για δικαστική χρήση συνήθως χρειάζεται επιπλέον
πιστοποίηση από δικηγόρο ή συμβολαιογράφο.

## Αυτόματη εκτέλεση

Απλούστερο: `fbwatch run --loop --every 2h` σε ένα τερματικό που μένει ανοιχτό.

Linux/macOS, cron κάθε 2 ώρες:

```
0 */2 * * * cd /διαδρομή/fbwatch && .venv/bin/fbwatch run >> data/run.log 2>&1
```

Windows, Task Scheduler: πρόγραμμα `C:\διαδρομή\fbwatch\.venv\Scripts\fbwatch.exe`,
ορίσματα `run`, φάκελος εκκίνησης ο φάκελος του έργου.

## Αντιμετώπιση προβλημάτων

- **`login_wall`**: το Facebook ζήτησε σύνδεση. Συμβαίνει για προσωπικά προφίλ (δεν υποστηρίζονται
  χωρίς login) ή αν η IP έχει στοχοποιηθεί από πολλά αιτήματα. Δοκίμασε αργότερα, αύξησε το
  `delay_between_sources_s`, ή χρησιμοποίησε άλλο δίκτυο.
- **`unavailable`**: το περιεχόμενο δεν είναι διαθέσιμο χωρίς σύνδεση ή η Page έχει περιορισμούς
  (ηλικία, χώρα) ή απαγορεύει embed.
- **`empty`**: η σελίδα φόρτωσε αλλά δεν αναγνωρίστηκαν posts. Πιθανότατα άλλαξε το markup του
  Facebook. Τρέξε `fbwatch check --dump` και στείλε το `.html` από το `data/debug/`. Οι σελέκτορες
  βρίσκονται στην κορυφή του `fbwatch/extract.py` και προσαρμόζονται εύκολα.
- **Λάθος ημερομηνίες**: το εργαλείο διαβάζει το `data-utime` ή τον τίτλο του timestamp. Η στήλη
  `posted_at_raw` δείχνει τι ακριβώς είδε, για έλεγχο.
- **Chromium δεν βρίσκεται**: τρέξε `playwright install chromium` ή δώσε `browser.executable_path`
  στο config ή τη μεταβλητή περιβάλλοντος `FBWATCH_CHROMIUM`.

## Νομικό πλαίσιο, συνοπτικά

Το εργαλείο συλλέγει μόνο δημόσιο περιεχόμενο και δεν κάνει login. Η αυτοματοποιημένη συλλογή
παραβαίνει τους όρους χρήσης του Facebook, πράγμα που μπορεί να οδηγήσει σε αποκλεισμό IP αλλά δεν
είναι ποινικό ζήτημα. Στην ΕΕ ισχύει ο GDPR: posts ιδιωτών είναι προσωπικά δεδομένα και η
συστηματική συλλογή τους χρειάζεται νομική βάση (δημοσιογραφία, έρευνα, νομική αξίωση). Για posts
οργανισμών, ΜΜΕ και δημόσιων προσώπων το ζήτημα είναι σαφώς μικρότερο. Αναδημοσίευση των
screenshots εγείρει θέματα πνευματικών δικαιωμάτων του συντάκτη.

## Ανάπτυξη

```bash
pip install -e ".[dev]"
pytest
```

Τα tests δεν χρειάζονται δίκτυο: χρησιμοποιούν τοπικά HTML στο `tests/fixtures/` που μιμούνται
τη δομή των plugins του Facebook.
