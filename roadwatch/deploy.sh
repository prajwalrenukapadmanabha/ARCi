#!/usr/bin/env bash
# Usage: ./deploy.sh [region]   (default ap-south-1)
set -euo pipefail
REGION="${1:-ap-south-1}"
sam build
sam deploy --stack-name roadwatch --region "$REGION" --resolve-s3 --capabilities CAPABILITY_IAM --no-confirm-changeset
API=$(aws cloudformation describe-stacks --stack-name roadwatch --region "$REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='ApiUrl'].OutputValue" --output text)
sed -i.bak "s|PASTE_YOUR_ApiUrl_OUTPUT_HERE|$API|" web/index.html
echo "API: $API"
echo "Open web/index.html in a browser (or host it on S3/Amplify)."
