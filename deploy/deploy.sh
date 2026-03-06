#!/bin/bash
# Run on server after every code push.
# Usage: bash /var/www/piramallease/Backend/deploy/deploy.sh

set -e

BASE="/var/www/piramallease"

echo "=== Pulling Backend ==="
cd $BASE/Backend
git pull

echo "=== Pulling Frontend ==="
cd $BASE/new-frontend
git pull

echo "=== Python packages ==="
$BASE/venv/bin/pip install -r $BASE/Backend/requirements.txt

echo "=== Django migrate + collectstatic ==="
cd $BASE/Backend
$BASE/venv/bin/python manage.py migrate --noinput
$BASE/venv/bin/python manage.py collectstatic --noinput

echo "=== Rebuild frontend ==="
cd $BASE/new-frontend
npm ci
npm run build

echo "=== Restart service ==="
systemctl restart piramallease

echo "Done."
systemctl status piramallease --no-pager
