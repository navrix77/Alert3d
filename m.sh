#!/bin/bash
# тимчасовий скрипт переносу даних NAVRYX SKY з ПК на сервер (ключ передається аргументом)
set -e
cd ~
curl -sL https://raw.githubusercontent.com/navrix77/alert3d/migrate-tmp/navryx-data.enc -o d.enc
openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -in d.enc -out d.tgz -pass pass:"$1"
tar tzf d.tgz | head -3
gcloud compute scp d.tgz navryx-sky:/tmp/d.tgz --zone europe-north1-b --quiet
gcloud compute ssh navryx-sky --zone europe-north1-b --quiet --command 'sudo systemctl stop navryx; cd /opt/navryx/app/data && sudo rm -f brain.sqlite-wal brain.sqlite-shm && sudo -u navryx tar xzf /tmp/d.tgz && sudo rm -f /tmp/d.tgz && sudo systemctl start navryx && sleep 10 && systemctl is-active navryx && sudo -u navryx /opt/navryx/venv/bin/python -c "import sqlite3;c=sqlite3.connect(\"brain.sqlite\");print(\"msg\",c.execute(\"select count(*) from msg\").fetchone()[0],\"trans\",c.execute(\"select count(*) from trans\").fetchone()[0])"; ls data 2>/dev/null; ls daily | head; curl -s -m 5 127.0.0.1:8080/healthz'
rm -f d.enc d.tgz
echo ПЕРЕНЕСЕНО
