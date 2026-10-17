#!/usr/bin/env bash
# Deploys labvisit to production: env file, static files, migrations, code.
# Usage: ./deploy.sh            (normal deploy)
#        ./deploy.sh --schedule (also re-registers scheduled jobs, after changing "events" or keep_warm)
set -euo pipefail
cd "$(dirname "$0")"

STAGE=production
PROFILE=$(python3 -c "import json;print(json.load(open('zappa_settings.json'))['$STAGE'].get('profile_name','default'))")
BUCKET=$(python3 -c "import json;print(json.load(open('zappa_settings.json'))['$STAGE']['s3_bucket'])")

if [ -z "${VIRTUAL_ENV:-}" ]; then
  source .venv-deploy/bin/activate
fi

echo "→ Uploading production.env.json"
aws s3 cp production.env.json "s3://$BUCKET/$STAGE.env.json" --profile "$PROFILE" --only-show-errors

echo "→ Collecting static files"
python manage.py collectstatic --noinput -v0

echo "→ Running migrations"
DATABASE_URL=$(python3 -c "import json;print(json.load(open('production.env.json'))['DATABASE_URL'])") \
  python manage.py migrate --noinput

echo "→ Updating code"
zappa update "$STAGE"

if [ "${1:-}" = "--schedule" ]; then
  echo "→ Updating scheduled jobs"
  zappa schedule "$STAGE"
fi

echo "✓ Deployed"
