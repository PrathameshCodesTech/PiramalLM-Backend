#!/bin/bash
# One-time server setup for piramallease.vibecopilot.ai
# Run as root AFTER cloning both repos:
#
#   mkdir -p /var/www/piramallease
#   git clone <BACKEND_REPO_URL>  /var/www/piramallease/Backend
#   git clone <FRONTEND_REPO_URL> /var/www/piramallease/new-frontend
#   bash /var/www/piramallease/Backend/deploy/setup.sh

set -e

DOMAIN="piramallease.vibecopilot.ai"
BASE="/var/www/piramallease"

echo "=== [1/8] System packages ==="
apt-get update -y
apt-get install -y python3 python3-pip python3-venv python3-dev \
    postgresql postgresql-contrib \
    nginx certbot python3-certbot-nginx \
    git curl build-essential libpq-dev

echo "=== [2/8] Node.js 20 ==="
curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
apt-get install -y nodejs

echo "=== [3/8] PostgreSQL ==="
DB_PASS=$(openssl rand -base64 24 | tr -d '/+=')
sudo -u postgres psql <<SQL
CREATE USER piramallease WITH PASSWORD '$DB_PASS';
CREATE DATABASE piramallease_db OWNER piramallease;
GRANT ALL PRIVILEGES ON DATABASE piramallease_db TO piramallease;
SQL

echo "=== [4/8] Python virtualenv ==="
python3 -m venv $BASE/venv
$BASE/venv/bin/pip install --upgrade pip
$BASE/venv/bin/pip install -r $BASE/Backend/requirements.txt

echo "=== [5/8] .env ==="
SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(50))")
cat > $BASE/Backend/.env <<ENV
DEBUG=False
SECRET_KEY=$SECRET_KEY
ALLOWED_HOSTS=$DOMAIN
DATABASE_URL=postgres://piramallease:$DB_PASS@localhost:5432/piramallease_db
CORS_ALLOWED_ORIGINS=https://$DOMAIN
ENV
echo ".env written."

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

cp $BASE/Backend/deploy/piramallease.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable piramallease
systemctl start piramallease

NGINX_CONF=/etc/nginx/sites-available/$DOMAIN
cp $BASE/Backend/deploy/nginx.conf $NGINX_CONF
ln -sf $NGINX_CONF /etc/nginx/sites-enabled/$DOMAIN
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx

certbot --nginx -d $DOMAIN --non-interactive --agree-tos -m admin@$DOMAIN

echo ""
echo "=============================="
echo " DONE — https://$DOMAIN"
echo "=============================="
systemctl status piramallease --no-pager
