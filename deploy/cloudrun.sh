#!/usr/bin/env bash
# Розгортання «Тривоги» на Cloud Run (europe-central2, як «Комора»).
# Секрети заздалегідь: gcloud secrets create tg-api-id / tg-api-hash / tg-session / alerts-token
set -euo pipefail
PROJECT="${PROJECT:?вкажи PROJECT=<gcp-project-id>}"
REGION="${REGION:-europe-central2}"
SERVICE="${SERVICE:-tryvoga}"

gcloud run deploy "$SERVICE" \
  --project "$PROJECT" --region "$REGION" --source . \
  --allow-unauthenticated \
  --min-instances 1 --max-instances 1 \
  --no-cpu-throttling --cpu 1 --memory 1Gi \
  --timeout 3600 --session-affinity
  
# max-instances 1: один слухач Telegram, щоб не дублювати сесію; WebSocket-клієнтів витримує сотні.
