#!/bin/bash
# One-time server setup for piramallease.vibecopilot.ai
# Run as root AFTER cloning both repos:
#
#   mkdir -p /var/www/piramallease
#   git clone https://github.com/PrathameshCodesTech/PiramalLM-Backend.git  /var/www/piramallease/Backend
#   git clone https://github.com/PrathameshCodesTech/NEW-piramal-frontend.git /var/www/piramallease/new-frontend
#   bash /var/www/piramallease/Backend/deploy/setup.sh

set -e

DOMAIN="piramallease.vibecopilot.ai"
BASE="/var/www/piramallease"
GUNICORN_PORT=8014   # free port on this server

echo "=== [1/8] Python 3.10 via deadsnakes PPA (Ubuntu 18.04) ==="
add-apt-repository -y ppa:deadsnakes/ppa
apt-get update -y
apt-get install -y python3.10 python3.10-venv python3.10-dev libpq-dev build-essential

echo "=== [2/8] Upgrade Node.js to 20 ==="
curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
apt-get install -y nodejs

echo "=== [3/8] PostgreSQL — create DB and user (PostgreSQL already installed) ==="
DB_PASS=$(openssl rand -base64 24 | tr -d '/+=')
sudo -u postgres psql <<SQL
DO \$\$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'piramallease') THEN
    CREATE USER piramallease WITH PASSWORD '$DB_PASS';
  END IF;
END
\$\$;
CREATE DATABASE piramallease_db OWNER piramallease;
GRANT ALL PRIVILEGES ON DATABASE piramallease_db TO piramallease;
SQL

echo "=== [4/8] Python virtualenv with Python 3.10 ==="
python3.10 -m venv $BASE/venv
$BASE/venv/bin/pip install --upgrade pip
$BASE/venv/bin/pip install -r $BASE/Backend/requirements.txt

echo "=== [5/8] .env ==="
SECRET_KEY=$(python3.10 -c "import secrets; print(secrets.token_urlsafe(50))")
cat > $BASE/Backend/.env <<ENV
DEBUG=False
SECRET_KEY=$SECRET_KEY
ALLOWED_HOSTS=$DOMAIN
DATABASE_URL=postgres://piramallease:$DB_PASS@localhost:5432/piramallease_db
CORS_ALLOWED_ORIGINS=https://$DOMAIN
ENV
echo ".env written to $BASE/Backend/.env"
echo "DB password: $DB_PASS  (save this!)"

echo "=== [6/8] Django migrate + collectstatic + superuser ==="
cd $BASE/Backend
$BASE/venv/bin/python manage.py migrate --noinput
$BASE/venv/bin/python manage.py collectstatic --noinput
$BASE/venv/bin/python manage.py createsuperuser

echo "=== [7/8] Build frontend ==="
cd $BASE/new-frontend
npm ci
npm run build

echo "=== [8/8] systemd + nginx + SSL ==="
mkdir -p /var/log/piramallease

# Inject the correct gunicorn port into the service file before copying
sed "s/127.0.0.1:8000/127.0.0.1:$GUNICORN_PORT/" \
    $BASE/Backend/deploy/piramallease.service > /etc/systemd/system/piramallease.service

systemctl daemon-reload
systemctl enable piramallease
systemctl start piramallease

# Inject the correct gunicorn port into the nginx config before copying
NGINX_CONF=/etc/nginx/sites-available/$DOMAIN
sed "s/127.0.0.1:8000/127.0.0.1:$GUNICORN_PORT/" \
    $BASE/Backend/deploy/nginx.conf > $NGINX_CONF
ln -sf $NGINX_CONF /etc/nginx/sites-enabled/$DOMAIN
nginx -t && systemctl reload nginx

# SSL via certbot (snap is more reliable on 18.04)
snap install --classic certbot 2>/dev/null || apt-get install -y certbot python3-certbot-nginx
certbot --nginx -d $DOMAIN --non-interactive --agree-tos -m admin@$DOMAIN

echo ""
echo "=============================="
echo " DONE — https://$DOMAIN"
echo "=============================="
systemctl status piramallease --no-pager
