#!/bin/bash
# NAVRYX SKY: віртуальна машина Google (те саме, що deploy-vm.bat, але для Cloud Shell у браузері).
# Запуск у Cloud Shell:  git clone -q https://github.com/navrix77/alert3d && bash alert3d/deploy/deploy-vm.sh navryx-sky
set -e
PROJECT=${1:-$(gcloud config get-value project 2>/dev/null)}
[ -z "$PROJECT" ] && { echo "[!] Вкажіть проєкт: bash deploy-vm.sh navryx-sky"; exit 1; }
VM=navryx-sky; ZONE=europe-north1-a; REGION=europe-north1; DOMAIN=sky.navryx.com.ua
DIR=$(cd "$(dirname "$0")" && pwd)
gcloud config set project "$PROJECT" >/dev/null
echo "Проєкт: $PROJECT   Зона: $ZONE"
echo "[1/4] Вмикаю Compute Engine (до 1-2 хв)..."
if ! gcloud services enable compute.googleapis.com; then
  echo "[!] Не вдалося. Найчастіше — до проєкту не підключено оплату:"
  echo "    https://console.cloud.google.com/billing/linkedaccount?project=$PROJECT"; exit 1
fi
echo "[2/4] Постійна IP-адреса"
gcloud compute addresses describe $VM-ip --region $REGION >/dev/null 2>&1 || gcloud compute addresses create $VM-ip --region $REGION
IP=$(gcloud compute addresses describe $VM-ip --region $REGION --format "value(address)")
echo "[3/4] Дозволяю вхід на 80/443 (лише для цієї машини)"
gcloud compute firewall-rules describe $VM-web >/dev/null 2>&1 || gcloud compute firewall-rules create $VM-web --allow tcp:80,tcp:443 --target-tags $VM --description "NAVRYX SKY web"
echo "[4/4] Віртуальна машина"
EXIST=$(gcloud compute instances list --filter="name=$VM" --format="value(zone.basename())")
if [ -z "$EXIST" ]; then
  # зона може тимчасово не мати вільних e2-small — пробуємо всі зони регіону
  for ZONE in europe-north1-a europe-north1-b europe-north1-c; do
    echo "   зона $ZONE..."
    if gcloud compute instances create $VM --zone $ZONE --machine-type e2-small \
      --image-family ubuntu-2404-lts-amd64 --image-project ubuntu-os-cloud --boot-disk-size 20GB --boot-disk-type pd-balanced \
      --address "$IP" --tags $VM --metadata domain=$DOMAIN --metadata-from-file startup-script="$DIR/vm-setup.sh"; then OK=1; break; fi
  done
  [ -z "${OK:-}" ] && { echo "[!] У жодній зоні europe-north1 зараз немає вільних машин. Спробуйте за годину."; exit 1; }
else
  echo "Машина вже є ($EXIST) — оновлюю скрипт запуску"
  gcloud compute instances add-metadata $VM --zone $EXIST --metadata domain=$DOMAIN --metadata-from-file startup-script="$DIR/vm-setup.sh"
fi
echo
echo "================================================================"
echo " Готово. IP-адреса сервера:   $IP"
echo " Перше встановлення триває 5-10 хв. Перевірка: http://$IP"
echo " DNS у imena.ua:  хост sky   тип A   значення $IP"
echo "================================================================"
