#!/bin/bash
# тимчасовий скрипт переносу даних NAVRYX SKY з ПК на сервер (ключ передається аргументом)
cd ~
if [ ! -f d.tgz ]; then
  curl -sL https://raw.githubusercontent.com/navrix77/alert3d/migrate-tmp/navryx-data.enc -o d.enc
  openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -in d.enc -out d.tgz -pass pass:"$1" || exit 1
fi
gcloud compute scp d.tgz navryx-sky:/tmp/d.tgz --zone europe-north1-b --quiet || exit 1
gcloud compute ssh navryx-sky --zone europe-north1-b --quiet --command 'sudo bash -s' <<'R'
systemctl stop navryx
cd /opt/navryx/app/data || { systemctl start navryx; exit 1; }
rm -f brain.sqlite-wal brain.sqlite-shm
tar xzf /tmp/d.tgz && chown -R navryx:navryx brain.sqlite learn.json sources_auto.json daily
rm -f /tmp/d.tgz
systemctl start navryx
sleep 10
systemctl is-active navryx
/opt/navryx/venv/bin/python -c "import sqlite3;c=sqlite3.connect('brain.sqlite');print('msg',c.execute('select count(*) from msg').fetchone()[0],'trans',c.execute('select count(*) from trans').fetchone()[0])"
ls daily | head -3
curl -s -m 5 127.0.0.1:8080/healthz; echo
R
rm -f d.enc d.tgz
echo ПЕРЕНЕСЕНО
