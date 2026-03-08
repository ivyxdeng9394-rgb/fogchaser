#!/bin/bash
# Run the live forecast pipeline and push updated manifest to trigger a Vercel redeploy.
# Usage: bash scripts/refresh_forecast.sh

set -e  # stop immediately if any command fails

cd "$(dirname "$0")/.."

# Load R2 credentials from .env
if [ -f .env ]; then
  export $(grep -v '^#' .env | xargs)
else
  echo "ERROR: .env file not found. Copy .env.example to .env and fill in your R2 credentials."
  exit 1
fi

echo "Running live forecast pipeline..."
python3 scripts/run_live_forecast.py

echo ""
echo "Done — forecast updated on Cloudflare R2."
