#!/usr/bin/env bash
# Перенесення ключів з локального .env.local на сервер NAVRYX SKY (запускає власник на своєму комп'ютері).
# Ключі йдуть напряму з вашого ПК на VM через gcloud (SSH), не через репозиторій і не через чат.
#   bash deploy/push-env.sh [шлях/до/.env.local]
# Що робить: копіює файл у /tmp на VM, додає/оновлює змінні в /opt/navryx/.env (інші рядки лишаються),
# права 600, видаляє тимчасовий файл і перезапускає сервіс. Нічого не друкує зі значень ключів.
set -euo pipefail
SRC=${1:-.env.local}
VM=navryx-sky; ZONE=${ZONE:-$(gcloud compute instances list --filter="name=$VM" --format="value(zone.basename())")}
[ -f "$SRC" ] || { echo "Немає файлу $SRC"; exit 1; }
echo "Змінні, які буде перенесено (лише назви):"; grep -E '^[A-Za-z_][A-Za-z0-9_]*=' "$SRC" | cut -d= -f1 | sed 's/^/  /'
gcloud compute scp "$SRC" "$VM:/tmp/navryx-env.new" --zone "$ZONE"
gcloud compute ssh "$VM" --zone "$ZONE" --command 'set -e
  T=/opt/navryx/.env; sudo touch $T
  while IFS= read -r ln; do
    case "$ln" in ""|\#*) continue;; esac
    k="${ln%%=*}"; k="${k#export }"
    # «groq=...» у вашому файлі → GROQ_API_KEY (так його шукає сервер; стара назва теж працює)
    [ "$k" = "groq" ] && ln="GROQ_API_KEY=${ln#*=}" && k=GROQ_API_KEY
    sudo sed -i "/^${k}=/d" $T
    echo "$ln" | sudo tee -a $T >/dev/null
  done < /tmp/navryx-env.new
  grep -q "^LLM_MODE=" $T || echo "LLM_MODE=shadow" | sudo tee -a $T >/dev/null
  shred -u /tmp/navryx-env.new 2>/dev/null || rm -f /tmp/navryx-env.new
  sudo chown navryx $T; sudo chmod 600 $T
  sudo systemctl restart navryx
  echo "Готово: змінних у .env на сервері: $(sudo grep -c "=" $T)"'
echo "Перевірте: https://sky.navryx.com.ua/api/llm  (має бути \"enabled\": true)"
