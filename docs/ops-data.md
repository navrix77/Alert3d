# Дані сервера для сесій аналізу (гілка `ops-data`)

Сервер (VM) сам рахує все на своїй повній базі й щогодини пушить результат в окрему гілку `ops-data`
(`app/ops_export.py`). Сесії самоосвіти й нічного розбору беруть дані звідти, а не з API.

## Увімкнути (один раз, власник)
1. GitHub → Settings → Developer settings → Fine-grained tokens → New token:
   доступ лише до репозиторію `navrix77/Alert3d`, Permissions → Contents: **Read and write**. Термін, наприклад, 1 рік.
2. У своєму `.env.local` додайте рядок `OPS_GIT_TOKEN=<токен>` і запустіть `bash deploy/push-env.sh`
   (або `push-env.bat`). Ключ іде прямо на VM через gcloud SSH, у репозиторій і чат не потрапляє. Сервіс перезапуститься.
3. За ~2 хв з'явиться гілка `ops-data`. Перевірка: https://github.com/navrix77/Alert3d/tree/ops-data

## Що в гілці
| файл | що це |
|---|---|
| `journal-72h.json.gz` | журнал публічних повідомлень каналів за 72 год, формат `scripts/backtest.py` |
| `selfcheck.json` | щоденний самоаналіз сервера (о ~05:40): падіння парсера, тезки, стрибки, бектест |
| `fusion.json`, `fc_calib_live.json` | перевірка злиття напрямку, калібрування прогнозу |
| `occupied.geojson` | окупована територія (для перевірки «вхід від кордону / фронту») |
| `status.json` | час вивантаження, коміт сервера, цілей за останню годину, `massive` (>100 → код не пушити) |

Бази push-підписок, візитів, `.env`, ключі не вивантажуються. Гілка завжди один коміт (force push), `main` не чіпається.

## Як користуватись у сесії
```
bash scripts/ops_fetch.sh                       # → data/ops/
python3 scripts/backtest.py data/ops/journal-72h.json.gz --test-from <unix-час>
```
Порядок: спершу `ops-data`; якщо гілки немає або `status.json` старіший за 3 год, пробувати API
`https://sky.navryx.com.ua/api/journal`; якщо й воно недоступне, записати це в журнал навчання.

Налаштування: `OPS_EXPORT_MIN` (типово 60), `OPS_EXPORT_HOURS` (типово 72), `OPS_GIT_REPO` (типово navrix77/Alert3d).
