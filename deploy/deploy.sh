#!/bin/bash
# Run on server after every code push.
# Usage: bash /var/www/piramallease/Backend/deploy/deploy.sh
#
# NOTE: Frontend must be built locally and uploaded separately:
#   cd new-frontend && npm run build
#   scp -i <pem> -r dist/ root@139.5.188.191:/var/www/piramallease/new-frontend/

set -e

BASE="/var/www/piramallease"

echo "=== Pulling Backend ==="
cd $BASE/Backend && git pull

echo "=== Python packages ==="
$BASE/venv/bin/pip install -r $BASE/Backend/requirements.txt

echo "=== Django migrate + collectstatic ==="
cd $BASE/Backend
$BASE/venv/bin/python manage.py migrate --noinput
$BASE/venv/bin/python manage.py collectstatic --noinput

echo "=== Restart service ==="
systemctl restart piramallease

echo "Done. Remember to upload new dist/ if frontend changed."
systemctl status piramallease --no-pager
