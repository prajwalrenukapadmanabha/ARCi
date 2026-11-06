"""Triggered by S3 uploads: ask a Bedrock vision model to verify and score the pothole."""
import json
import os
import re

import boto3

TABLE = os.environ.get("TABLE", "")
BUCKET = os.environ.get("BUCKET", "")
MODEL_ID = os.environ.get("MODEL_ID", "")

_ddb = None
_s3 = None
_br = None

PROMPT = (
    "You inspect road photos for a civic safety app. Reply with JSON only, no prose: "
    '{"is_pothole": true or false, "severity": 1 to 5, '
    '"hazard_for_two_wheelers": "low" or "medium" or "high", "reason": "max 20 words"}. '
    "Severity 1 = tiny crack, 3 = clear hole that can damage a tyre, "
    "5 = deep hole or broken edge that can throw a rider. "
    "If the image is not a road surface, set is_pothole to false."
)


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


def bedrock():
    global _br
    if _br is None:
        _br = boto3.client("bedrock-runtime")
    return _br


def parse_model_json(text):
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("no JSON in model reply")
    data = json.loads(m.group(0))
    data["is_pothole"] = data.get("is_pothole") in (True, "true", "True")
    data["severity"] = max(1, min(5, int(data.get("severity", 1))))
    hz = str(data.get("hazard_for_two_wheelers", "medium")).lower()
    data["hazard_for_two_wheelers"] = hz if hz in ("low", "medium", "high") else "medium"
    data["reason"] = str(data.get("reason", ""))[:120]
    return data


def classify(image_bytes):
    out = bedrock().converse(
        modelId=MODEL_ID,
        messages=[{"role": "user", "content": [
            {"image": {"format": "jpeg", "source": {"bytes": image_bytes}}},
            {"text": PROMPT},
        ]}],
        inferenceConfig={"maxTokens": 200, "temperature": 0},
    )
    return parse_model_json(out["output"]["message"]["content"][0]["text"])


def set_status(rid, status, extra=None):
    names = {"#s": "status"}
    vals = {":s": status}
    expr = "SET #s = :s"
    for i, (k, v) in enumerate((extra or {}).items()):
        names[f"#k{i}"] = k
        vals[f":v{i}"] = v
        expr += f", #k{i} = :v{i}"
    if status in ("verified", "rejected"):
        expr += " REMOVE #ttl"
        names["#ttl"] = "ttl"
    table().update_item(
        Key={"id": rid},
        UpdateExpression=expr,
        ExpressionAttributeNames=names,
        ExpressionAttributeValues=vals,
        ConditionExpression="attribute_exists(id)",
    )


def handler(event, _ctx):
    for rec in event.get("Records", []):
        key = rec["s3"]["object"]["key"]
        rid = key.rsplit(".", 1)[0]
        try:
            img = s3().get_object(Bucket=BUCKET, Key=key)["Body"].read()
            r = classify(img)
            if r["is_pothole"]:
                set_status(rid, "verified", {
                    "severity": r["severity"],
                    "hazard": r["hazard_for_two_wheelers"],
                    "reason": r["reason"],
                })
            else:
                set_status(rid, "rejected", {"reason": r["reason"]})
                s3().delete_object(Bucket=BUCKET, Key=key)  # drop non-pothole photos early
        except Exception as e:  # keep the report for manual review instead of losing it
            print("analyze failed", rid, repr(e))
            try:
                set_status(rid, "review")
            except Exception as e2:
                print("could not mark review", rid, repr(e2))
