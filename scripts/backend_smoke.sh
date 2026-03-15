#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8088/api}"
TOKEN="${TOKEN:-dev:alice:alice@example.com:Alice}"
TMP_FILE="$(mktemp /tmp/smoke-track-XXXXXX.mp3)"

cleanup() {
  rm -f "$TMP_FILE"
}
trap cleanup EXIT

echo "[1/6] Verify auth"
VERIFY_JSON="$(curl -sS -X POST "$BASE_URL/auth/verify" -H 'Content-Type: application/json' -d '{"id_token":"'"$TOKEN"'"}')"
echo "$VERIFY_JSON"

echo "[2/6] Request pre-signed upload URL"
PRESIGN_JSON="$(curl -sS -X POST "$BASE_URL/uploads/presign" \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"filename":"smoke.mp3","content_type":"audio/mpeg","title":"Smoke Track","artist":"Smoke Artist","visibility":"private"}')"

echo "$PRESIGN_JSON"

TRACK_ID="$(python3 - <<'PY' "$PRESIGN_JSON"
import json, sys
print(json.loads(sys.argv[1])["track_id"])
PY
)"
OBJECT_KEY="$(python3 - <<'PY' "$PRESIGN_JSON"
import json, sys
print(json.loads(sys.argv[1])["object_key"])
PY
)"
UPLOAD_URL="$(python3 - <<'PY' "$PRESIGN_JSON"
import json, sys
print(json.loads(sys.argv[1])["upload_url"])
PY
)"
UPLOAD_HOST="$(python3 - <<'PY' "$UPLOAD_URL"
import sys
from urllib.parse import urlparse
print(urlparse(sys.argv[1]).hostname or "")
PY
)"
UPLOAD_PORT="$(python3 - <<'PY' "$UPLOAD_URL"
import sys
from urllib.parse import urlparse
parsed = urlparse(sys.argv[1])
print(parsed.port or (443 if parsed.scheme == "https" else 80))
PY
)"

echo "[3/6] Upload file to MinIO using pre-signed URL"
printf 'SMOKE_AUDIO_CONTENT' > "$TMP_FILE"
if [[ "$UPLOAD_HOST" == "minio" ]]; then
  curl -sS -X PUT "$UPLOAD_URL" \
    --resolve "minio:${UPLOAD_PORT}:127.0.0.1" \
    -H 'Content-Type: audio/mpeg' \
    --data-binary "@$TMP_FILE" >/dev/null
else
  curl -sS -X PUT "$UPLOAD_URL" -H 'Content-Type: audio/mpeg' --data-binary "@$TMP_FILE" >/dev/null
fi

echo "[4/6] Mark upload complete"
COMPLETE_JSON="$(curl -sS -X POST "$BASE_URL/uploads/complete" \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"track_id":"'"$TRACK_ID"'","object_key":"'"$OBJECT_KEY"'"}')"

echo "$COMPLETE_JSON"

echo "[5/6] Poll track status"
for _ in $(seq 1 20); do
  TRACK_JSON="$(curl -sS "$BASE_URL/tracks/$TRACK_ID" -H "Authorization: Bearer $TOKEN")"
  STATUS="$(python3 - <<'PY' "$TRACK_JSON"
import json, sys
print(json.loads(sys.argv[1])["status"])
PY
)"

  if [[ "$STATUS" == "published" ]]; then
    echo "$TRACK_JSON"
    echo "[6/6] Smoke flow succeeded"
    exit 0
  fi

  sleep 1
done

echo "Track did not reach published status in time"
exit 1
