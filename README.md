# labvisit

Online booking for at-home lab sample collection, with automatic medical order reading.

A patient uploads a photo or PDF of their medical order. A vision model reads the exams as written, our own matcher maps them to the lab's catalog, the patient fixes the list, picks how they'll pay, and gets a quote with prep instructions. One deployment serves many labs, each on its own subdomain.

## Run it locally

```bash
uv sync
cp .env.example .env
uv run python manage.py migrate
uv run python manage.py seed_demo          # demo lab "biodata", placeholder prices
uv run python manage.py createsuperuser
uv run python manage.py runserver
```

Open http://localhost:8000 (uses `DEFAULT_LAB_SLUG`) or http://biodata.localhost:8000. The admin is at `/admin/`.

## Reading orders

`READER_PROVIDER=fake` returns a fixed list of exams, so the whole flow works without an API key. To read real images, set:

```
READER_PROVIDER=gemini
GEMINI_API_KEY=...
JOBS_BACKEND=thread
```

Only use the Gemini free tier with your own or made-up orders: on unpaid usage Google may use the content to improve its products. Real patient orders need a paid tier.

## Layout

- `labs/` the Lab model and the middleware that picks the lab from the subdomain
- `catalog/` exams, coverages and prices, managed from the Django admin
- `orders/` upload, reading (`reader.py`), matching (`matching.py`), background jobs (`jobs.py`), and the patient pages
- `templates/`, `static/` Django templates with HTMX

## Tests

```bash
uv run python manage.py test
```

## WhatsApp

Patients can book by WhatsApp with the same reading, matching and pricing as the web. The conversation lives in `whatsapp/flow.py`.

Try it in the terminal, no Meta account needed:

```bash
uv run python manage.py whatsapp_chat --lab biodata
```

To connect a real number (WhatsApp Cloud API):

1. Create an app at developers.facebook.com, add the WhatsApp product and register the number.
2. In `.env`: `WHATSAPP_BACKEND=meta`, `WHATSAPP_ACCESS_TOKEN` (a permanent system user token), `WHATSAPP_APP_SECRET`, a `WHATSAPP_VERIFY_TOKEN` of your choice, and `SITE_URL`.
3. In the admin, set the lab's "Whatsapp phone number id".
4. In Meta, set the webhook to `https://<your domain>/whatsapp/webhook/` with the same verify token, and subscribe to the `messages` field. For local testing, expose your server with `cloudflared tunnel --url http://localhost:8000`.

## Lab panel

Lab staff see booked visits at `/panel/` on the lab's subdomain. Create a user in the admin and add them as a staff user on the lab's page; superusers can open any lab's panel. From an order the staff can confirm, mark as done or cancel a visit (cancelling frees the hour) and keep internal notes.

## Deploy (AWS Lambda + Neon)

Production runs on Lambda through Zappa, with Postgres on Neon and order files in a private S3 bucket. Secrets live in an env file on S3 that Zappa loads at startup, never in the repo.

1. Neon: create a project in AWS São Paulo (`sa-east-1`) and a `labvisit` database; copy the pooled connection string.
2. S3: create two private buckets in `sa-east-1`, `labvisit-zappa-deploys` and `labvisit-media`.
3. Copy `production.env.example.json` to `production.env.json`, fill it in and upload it to `s3://labvisit-zappa-deploys/production.env.json`.
4. ACM (region `us-east-1`): request a certificate for `*.lab.compile.cl` and validate it with the CNAME record in Cloudflare.
5. Copy `zappa_settings.example.json` to `zappa_settings.json` and put the certificate ARN in it.
6. Deploy from a plain virtualenv (Zappa needs one):

       uv venv .venv-deploy --python 3.12 && source .venv-deploy/bin/activate
       uv pip install -r pyproject.toml --group deploy
       python manage.py collectstatic --noinput
       zappa deploy production
       zappa manage production migrate
       zappa manage production "seed_demo"
       zappa certify production

7. Cloudflare: add a CNAME `*.lab` pointing to the CloudFront domain that `zappa certify` prints (DNS only, not proxied).
8. Meta: change the webhook URL to `https://biodata.lab.compile.cl/whatsapp/webhook/`.

Later deploys are `./deploy.sh`: it uploads `production.env.json`, collects static files, runs the migrations and then updates the code. Add `--schedule` after changing scheduled jobs. Order files, WhatsApp messages and unbooked quotes older than `RETENTION_DAYS` (90) are deleted every night by `purge_old_data`.
