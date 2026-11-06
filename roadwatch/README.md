# RoadWatch

Citizens photograph a pothole; a Bedrock vision model verifies it and scores severity; verified reports appear on a public map, worst first.

## Layout
- template.yaml: SAM/CloudFormation (S3, DynamoDB with TTL, HTTP API, two Lambdas)
- src/api.py: POST /upload-url, GET /reports
- src/analyze.py: S3-triggered Bedrock classification
- web/index.html: map, photo upload, ranked list, CSV export
- tests/test_logic.py: unit tests (pytest, mocks only, no AWS needed)
- deploy.sh: one-command deploy

## Deploy
1. Install AWS CLI and SAM CLI, run `aws configure`.
2. In the Bedrock console, enable access to a vision-capable model in your region.
3. `./deploy.sh ap-south-1`
4. Host web/index.html over HTTPS (S3/Amplify/Netlify); phone GPS needs HTTPS.

## Test
`pip install boto3 pytest && pytest tests`

## Known limits
No login, so abuse is limited only by API throttling (10 req/s). AI severity is an estimate. Not field-tested.
