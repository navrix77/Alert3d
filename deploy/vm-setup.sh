#!/bin/bash
# NAVRYX SKY на віртуальній машині Google (Ubuntu 24.04). Запускається як startup-script при кожному старті VM:
# перший раз — усе ставить, далі — лише перевіряє, що служби працюють.
set -u
exec >>/var/log/navryx-setup.log 2>&1
echo "=== $(date) ==="
MD=http://metadata.google.internal/computeMetadata/v1/instance/attributes
DOMAIN=$(curl -sf -H Metadata-Flavor:Google $MD/domain || echo sky.navryx.com.ua)
REPO=$(curl -sf -H Metadata-Flavor:Google $MD/repo || echo https://github.com/navrix77/alert3d)
H=/opt/navryx

if [ ! -f $H/.installed ]; then
  # 2 ГБ підкачки: e2-small має 2 ГБ RAM, а збірка залежностей і голоси Piper люблять пам'ять
  if [ ! -f /swapfile ]; then fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile && echo '/swapfile none swap sw 0 0' >> /etc/fstab; fi
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -q && apt-get install -yq python3-venv python3-pip git caddy
  id navryx >/dev/null 2>&1 || useradd -r -m -d $H -s /usr/sbin/nologin navryx
  [ -d $H/app/.git ] || sudo -u navryx git clone -q "$REPO" $H/app
  sudo -u navryx python3 -m venv $H/venv
  sudo -u navryx $H/venv/bin/pip install -q -r $H/app/requirements.txt pytest
  sudo -u navryx $H/venv/bin/pip install -q --no-deps ukrainian-word-stress || true
  (cd $H/app && sudo -u navryx $H/venv/bin/python scripts/build_gazetteer.py) || true
  touch $H/.env && chown navryx $H/.env && chmod 600 $H/.env

  cat > /etc/systemd/system/navryx.service <<UNIT
[Unit]
Description=NAVRYX SKY
After=network-online.target
Wants=network-online.target
[Service]
User=navryx
WorkingDirectory=$H/app
Environment=LAN_TLS=0 PYTHONUNBUFFERED=1
EnvironmentFile=-$H/.env
ExecStart=$H/venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8080 --proxy-headers --forwarded-allow-ips=127.0.0.1 --ws-ping-interval 20
Restart=always
RestartSec=3
[Install]
WantedBy=multi-user.target
UNIT

  # Автооновлення: кожні 5 хв дивимося GitHub; нова версія ставиться лише якщо пройшли тести, інакше лишається попередня
  cat > $H/update.sh <<'UPD'
#!/bin/bash
set -u
cd /opt/navryx/app || exit 1
git fetch -q origin main || exit 0
OLD=$(git rev-parse HEAD); NEW=$(git rev-parse origin/main)
[ "$OLD" = "$NEW" ] && exit 0
git reset -q --hard "$NEW"
if git diff --name-only "$OLD" "$NEW" | grep -q '^requirements.txt$'; then /opt/navryx/venv/bin/pip install -q -r requirements.txt; fi
if /opt/navryx/venv/bin/python -m pytest -q tests >/tmp/navryx-tests.log 2>&1; then
  echo "$(date) оновлено $OLD -> $NEW"
  sudo /bin/systemctl restart navryx
else
  echo "$(date) тести не пройшли на $NEW — лишаю $OLD"; git reset -q --hard "$OLD"
fi
UPD
  chmod 755 $H/update.sh && chown navryx $H/update.sh
  echo "navryx ALL=(root) NOPASSWD: /bin/systemctl restart navryx" > /etc/sudoers.d/navryx && chmod 440 /etc/sudoers.d/navryx

  cat > /etc/systemd/system/navryx-update.service <<UNIT
[Unit]
Description=NAVRYX SKY — оновлення з GitHub
[Service]
Type=oneshot
User=navryx
ExecStart=$H/update.sh
StandardOutput=append:/var/log/navryx-update.log
UNIT
  cat > /etc/systemd/system/navryx-update.timer <<UNIT
[Unit]
Description=NAVRYX SKY — перевірка оновлень кожні 5 хв
[Timer]
OnBootSec=2min
OnUnitActiveSec=5min
[Install]
WantedBy=timers.target
UNIT
  touch /var/log/navryx-update.log && chown navryx /var/log/navryx-update.log

  # HTTPS-сертифікат Let's Encrypt Caddy отримає сам, щойно домен вказуватиме на цю машину; до того працює http://IP
  cat > /etc/caddy/Caddyfile <<CADDY
$DOMAIN {
	encode gzip
	reverse_proxy 127.0.0.1:8080
}
http:// {
	encode gzip
	reverse_proxy 127.0.0.1:8080
}
CADDY
  systemctl daemon-reload
  systemctl enable --now navryx navryx-update.timer
  systemctl restart caddy
  touch $H/.installed
  echo "встановлено"
else
  systemctl start navryx caddy navryx-update.timer
fi
