# Секрети в репозиторії: `secrets/env.enc`

## Поточний стан
- `secrets/env.enc` лежить у публічному репо навмисно. Це **не відкритий текст**: `.env.local` зашифровано
  гібридно (RSA-OAEP + AES) ПУБЛІЧНИМ ключем сервера (`/api/admin/envkey`). Приватний ключ є лише на VM
  (`/opt/navryx/.navryx_envkey.pem`, поза репозиторієм).
- Залежності (видаляти файл без міграції НЕ можна):
  - `app/secrets_sync.py` (`apply_pending`) — сервер кожні ~5 хв після оновлення читає `secrets/env.enc`, розшифровує й дописує змінні у свій `.env`; хеш застосованого лежить у `.navryx_envkey.applied`.
  - `.github/workflows/keys.yml` — генерує й коммітить цей файл з GitHub-секретів `SKY_ENV`, `GOOGLE_TTS_KEY`, `GEMINI_API_KEY`.
  - `push-env.bat` / update-потік VM покладаються на цю доставку.
- Відсутність файлу безпечна: `apply_pending()` повертає `[]`.

## Ризики
1. Шифротекст публічний і назавжди лишається в історії git. Якщо приватний ключ сервера колись витече (бекап VM, знімок диска, логи), усі ВЕРСІЇ `env.enc` з історії розшифруються ретроспективно.
2. Відсутність forward secrecy: один RSA-ключ на всі версії.
3. Кожен коміт `keys.yml` додає нову версію шифротексту в історію.
4. Метадані (розмір, час змін, поле `fp`) видно всім.

## Кроки міграції (рекомендований порядок)
1. **Ротація ключів зараз**, незалежно від решти: перевипустити все, що лежало в `.env.local` (Telegram API/сесія, Google TTS, Gemini, alerts-токен, ADMIN_TOKEN, VAPID/push, LLM-ключі). Старі значення вважати скомпрометованими на випадок майбутнього витоку приватного ключа.
2. **Ротація серверної пари RSA**: видалити `.navryx_envkey.pem` на VM, дати серверу згенерувати нову, перезапустити `keys.yml` (шифрує вже новим публічним ключем). Старий `env.enc` у історії стає нерозшифровним для нової пари, але зберігається шифротекст під старим ключем, тому п. 1 обов'язковий.
3. **Перейти на доставку без репо** (один з варіантів):
   - GitHub Actions -> SSH/scp на VM напряму в `/opt/navryx/.env` (секрет `SKY_ENV` лишається лише в GitHub Secrets);
   - Google Secret Manager (`deploy/cloudrun.sh` уже використовує `gcloud secrets`) + читання при старті;
   - `sops`+age з ключем лише на VM.
4. Після того як сервер читає секрети новим каналом: у `keys.yml` прибрати крок коміту `secrets/env.enc`; в `secrets_sync.apply_pending` лишити читання як fallback ще на один реліз, потім видалити модуль і файл (`git rm secrets/env.enc`), додати `secrets/` у `.gitignore`.
5. **Історія git**: після ротації (п. 1-2) переписування історії не обов'язкове, бо вміст застарілий. Якщо все ж потрібне: `git filter-repo --path secrets/env.enc --invert-paths`, force-push, попередити всіх клонувальників (клони/форки/кеші GitHub зберігають старі коміти; для повного видалення звернутись у GitHub Support). Не робити до завершення п. 1-3.
6. Увімкнути GitHub secret scanning + push protection, додати `gitleaks` у CI.

## Що змінено в коді в цій гілці
Лише додано заголовок `Content-Security-Policy-Report-Only` (див. `app/main.py`); `env.enc`, `secrets_sync.py` і workflow не чіпались.

## CSP: чому Report-Only
Фронт використовує inline-скрипти (Meta Pixel, заставка, реєстрація SW), атрибути `style=`, `onclick=` у app.js/arsenal.js/sound.js, воркери MapLibre з `blob:`, `unpkg.com` (deck.gl, jsPDF), тайли OpenFreeMap/ArcGIS/NASA GIBS/AWS terrarium/Google 3D Tiles. Тому політика допускає `'unsafe-inline'` і йде в режимі звітування; блокування вмикається `CSP_ENFORCE=1` після перевірки консолі браузера (в т.ч. встановленої PWA і Capacitor-збірки). Подальше посилення: винести inline-скрипти у файли, перейти на nonce, прибрати `onclick=`.
