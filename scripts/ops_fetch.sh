#!/usr/bin/env bash
# Забрати свіжі дані сервера з гілки ops-data (їх щогодини пушить сам сервер, app/ops_export.py) у data/ops/.
# Для сесій, яким недоступний sky.navryx.com.ua. Далі, наприклад:
#   python3 scripts/backtest.py data/ops/journal-72h.json.gz
#   python3 -c "import json;print(json.load(open('data/ops/status.json')))"   # massive: true → код не пушити
set -euo pipefail
cd "$(dirname "$0")/.."
git fetch -q origin ops-data
rm -rf data/ops && mkdir -p data/ops
git archive origin/ops-data | tar -x -C data/ops
python3 -c "import json;s=json.load(open('data/ops/status.json'));print('ops-data:',s['utc'],'UTC, повідомлень',s['rows'],', цілей за годину',s['targets_last_hour'],', масована' if s['massive'] else '')"
