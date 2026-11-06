import json, os, sys
from unittest import mock

os.environ.update(TABLE="t", BUCKET="b", MODEL_ID="m", AWS_DEFAULT_REGION="ap-south-1",
                  AWS_ACCESS_KEY_ID="x", AWS_SECRET_ACCESS_KEY="x")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import analyze, api  # noqa: E402


def test_parse_clamps_and_cleans():
    r = analyze.parse_model_json('Sure! {"is_pothole": true, "severity": 9, "hazard_for_two_wheelers": "EXTREME", "reason": "deep"}')
    assert r["is_pothole"] and r["severity"] == 5 and r["hazard_for_two_wheelers"] == "medium"


def test_parse_rejects_prose():
    try:
        analyze.parse_model_json("no json here")
        assert False
    except ValueError:
        pass


def test_upload_validates_coordinates():
    assert api.handler({"routeKey": "POST /upload-url", "body": json.dumps({"lat": 999, "lng": 0})}, None)["statusCode"] == 400
    assert api.handler({"routeKey": "POST /upload-url", "body": "{}"}, None)["statusCode"] == 400


def test_upload_returns_url():
    t, s = mock.Mock(), mock.Mock()
    s.generate_presigned_url.return_value = "https://example/put"
    with mock.patch.object(api, "table", return_value=t), mock.patch.object(api, "s3", return_value=s):
        r = api.handler({"routeKey": "POST /upload-url", "body": json.dumps({"lat": 12.97, "lng": 77.59})}, None)
    assert r["statusCode"] == 200 and json.loads(r["body"])["uploadUrl"] == "https://example/put"
    assert t.put_item.call_args.kwargs["Item"]["status"] == "pending"


def test_list_only_verified_sorted():
    t = mock.Mock()
    t.scan.return_value = {"Items": [
        {"id": "a", "status": "verified", "severity": 2, "lat": "1", "lng": "1", "created": 1},
        {"id": "b", "status": "pending"},
        {"id": "c", "status": "verified", "severity": 5, "lat": "2", "lng": "2", "created": 2},
    ]}
    with mock.patch.object(api, "table", return_value=t):
        body = json.loads(api.handler({"routeKey": "GET /reports"}, None)["body"])
    assert [x["id"] for x in body] == ["c", "a"]


def test_handler_marks_review_on_failure():
    ev = {"Records": [{"s3": {"object": {"key": "abc.jpg"}}}]}
    s = mock.Mock(); s.get_object.side_effect = RuntimeError("boom")
    with mock.patch.object(analyze, "s3", return_value=s), mock.patch.object(analyze, "set_status") as ss:
        analyze.handler(ev, None)
    ss.assert_called_with("abc", "review")
