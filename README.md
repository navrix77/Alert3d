# NAVRYX SKY — повітряна обстановка наживо (колишня «Тривога»)

Живий агрегатор повітряних загроз:
- **цілі** — склеює повідомлення моніторингових каналів у треки;
- **курс і прогноз маршруту**;
- **червоний/жовтий рівні областей** (офіційні тривоги + трекер);
- **картка цілі** з відстанню й ETA до дому та режимом «стежити»;
- **супутникова карта**.

## Архітектура

Один контейнер на Cloud Run (`min-instances=1`, `max-instances=1`):

| Модуль | Що робить |
|---|---|
| `app/telegram_src.py` | Telethon слухає вайтлист каналів у реальному часі, після рестарту дочитує останні 30 хв |
| `app/parser.py` | тип цілі, кількість, позиція, список «курсом на», фільтр безпеки (ППО/влучання не публікуються) |
| `app/geo.py` | газетир: КАТОТТГ (укр.) + OSM (укр./рос. назви), відмінки, фонетичне зіставлення рос.↔укр. |
| `app/tracker.py` | склеювання в треки, позиція вздовж маршруту, рівні областей |
| `app/alerts.py` | офіційні тривоги alerts.in.ua: тривога на всю область — червоний, на частину — жовтий |
| `app/main.py` | `/api/state`, WebSocket `/ws` (знімок кожні 2 с), статика PWA |
| `web/` | PWA на MapLibre: супутник Esri + підписи OpenFreeMap, іконки цілей з курсом і ×N, картка цілі |

Якщо джерела мовчать понад 20 с, клієнт показує «Немає звʼязку — це не відбій».

## Локальний запуск (демо на записаній ночі 29→30.10.2026)

```bash
pip install -r requirements.txt
REPLAY=1 REPLAY_FROM_MIN=420 uvicorn app.main:app --port 8080
# відкрити http://localhost:8080
```

## Підключення живих даних

1. **Telegram.** Заведи окремий акаунт і підпишися ним на канали з `app/config.py`. Потім на своєму компʼютері виконай `python scripts/telegram_login.py`. Отримаєш `TG_SESSION`.
2. **Офіційні тривоги.** Отримай токен на https://alerts.in.ua/api-request.
3. **Секрети в Google Cloud** (значення вводиш сам, нікому не пересилаєш):

   ```bash
   printf '%s' "<api_id>"     | gcloud secrets create tg-api-id    --data-file=-
   printf '%s' "<api_hash>"   | gcloud secrets create tg-api-hash  --data-file=-
   printf '%s' "<TG_SESSION>" | gcloud secrets create tg-session   --data-file=-
   printf '%s' "<token>"      | gcloud secrets create alerts-token --data-file=-
   ```

4. **Розгортання:** `PROJECT=<id> ./deploy/cloudrun.sh`.

## Тести

```bash
python -m pytest -q
```

Серед тестів є реплей реальної ночі.
