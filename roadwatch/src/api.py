"""RoadWatch API: issue upload links and list verified reports."""
import json
import os
import time
import uuid

import boto3

TABLE = os.environ.get("TABLE", "")
BUCKET = os.environ.get("BUCKET", "")
PENDING_TTL = 24 * 3600  # unverified rows vanish after a day

_ddb = None
_s3 = None


def table():
    global _ddb
    if _ddb is None:
        _ddb = boto3.resource("dynamodb").Table(TABLE)
    return _ddb


def s3():
    global _s3
    if _s3 is None:
        _s3 = boto3.client("s3")
    return _s3


def resp(code, body):
    return {
        "statusCode": code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body, default=str),
    }


def parse_point(body):
    lat, lng = float(body["lat"]), float(body["lng"])
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        raise ValueError("coordinates out of range")
    return lat, lng


def create_upload(event):
    try:
        body = json.loads(event.get("body") or "{}")
        lat, lng = parse_point(body)
    except (KeyError, ValueError, TypeError):
        return resp(400, {"error": "valid lat and lng are required"})
    rid = uuid.uuid4().hex[:12]
    now = int(time.time())
    table().put_item(Item={
        "id": rid,
        "status": "pending",
        "lat": str(round(lat, 6)),
        "lng": str(round(lng, 6)),
        "note": str(body.get("note", ""))[:200],
        "created": now,
        "ttl": now + PENDING_TTL,
    })
    url = s3().generate_presigned_url(
        "put_object",
        Params={"Bucket": BUCKET, "Key": f"{rid}.jpg", "ContentType": "image/jpeg"},
        ExpiresIn=300,
    )
    return resp(200, {"id": rid, "uploadUrl": url})


def list_reports():
    items, kwargs = [], {}
    while True:
        page = table().scan(**kwargs)
        items += page.get("Items", [])
        if "LastEvaluatedKey" not in page or len(items) > 5000:
            break
        kwargs["ExclusiveStartKey"] = page["LastEvaluatedKey"]
    ok = [i for i in items if i.get("status") == "verified"]
    ok.sort(key=lambda i: (int(i.get("severity", 0)), int(i.get("created", 0))), reverse=True)
    public = [
        {k: i.get(k) for k in ("id", "lat", "lng", "severity", "hazard", "reason", "created")}
        for i in ok[:500]
    ]
    return resp(200, public)


def handler(event, _ctx):
    route = event.get("routeKey", "")
    if route == "POST /upload-url":
        return create_upload(event)
    if route == "GET /reports":
        return list_reports()
    return resp(404, {"error": "not found"})
