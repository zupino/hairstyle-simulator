#!/usr/bin/env bash
set -eu
cd "$(dirname "$0")/.."

: "${BFL_API_KEY:?Export the BFL API key before deploying}"
: "${SECRET_KEY:?Export the JWT signing secret before deploying}"
: "${ADMIN_PASSWORD:?Export the bootstrap admin password before deploying}"
if (( ${#ADMIN_PASSWORD} < 8 )); then
  echo "ADMIN_PASSWORD must contain at least 8 characters" >&2
  exit 1
fi

# gcloud supports a custom dictionary separator. Choose one absent from every
# value so passwords can include commas, spaces and shell punctuation.
# Distinct runtime names avoid a type collision while gcloud removes old secret bindings.
settings=("SALON_BFL_API_KEY=$BFL_API_KEY" "SALON_SECRET_KEY=$SECRET_KEY" "SALON_ADMIN_PASSWORD=$ADMIN_PASSWORD")
for name in BFL_MODEL ADMIN_USERNAME ACCESS_TOKEN_TTL DB_PATH STORAGE_PATH; do
  if [[ -n ${!name:-} ]]; then settings+=("$name=${!name}"); fi
done
separator='@'
while [[ "${settings[*]}" == *"$separator"* ]]; do separator+="@"; done
runtime_vars="^${separator}^${settings[0]}"
for setting in "${settings[@]:1}"; do runtime_vars+="$separator$setting"; done

exec gcloud run deploy hairstyle-simulator --source . --region europe-west1 \
  --min-instances 0 --max-instances 1 --allow-unauthenticated \
  --remove-secrets=BFL_API_KEY,SECRET_KEY,ADMIN_PASSWORD \
  --set-env-vars "$runtime_vars" "$@"
