"""Voice agent webhook: simulates the requests Vapi sends during a call."""
import uuid


def tool_call(client, name, args, call_id="call-1"):
    payload = {
        "message": {
            "type": "tool-calls",
            "call": {"id": call_id, "customer": {"number": "+17325550123"}},
            "toolCallList": [{"id": "tc-1", "type": "function", "function": {"name": name, "arguments": args}}],
        }
    }
    r = client.post("/vapi/webhook", json=payload)
    assert r.status_code == 200
    result = r.json()["results"][0]
    assert result["toolCallId"] == "tc-1"
    return result["result"]


def test_full_registration_then_returning_caller(client, jane):
    assert tool_call(client, "find_patient_by_phone", {"phone_number": "7325550123"}).startswith("NO_MATCH")
    saved = tool_call(client, "register_patient", {**jane, "email": "jane at example dot com"})
    assert saved.startswith("SAVED")
    # Data is persisted and visible through the REST API.
    patients = client.get("/patients").json()["data"]
    assert len(patients) == 1 and patients[0]["email"] == "jane@example.com"
    # Second call: same phone number is recognised.
    found = tool_call(client, "find_patient_by_phone", {"phone_number": "732 555 0123"}, call_id="call-2")
    assert found.startswith("MATCH_FOUND") and "Jane" in found


def test_invalid_fields_come_back_for_reprompt(client, jane):
    result = tool_call(client, "register_patient", {**jane, "date_of_birth": "12/31/2999", "phone_number": "123"})
    assert result.startswith("NOT_SAVED")
    assert "date_of_birth" in result and "phone_number" in result
    assert client.get("/patients").json()["data"] == []


def test_duplicate_phone_needs_force_new(client, jane):
    tool_call(client, "register_patient", jane)
    dup = tool_call(client, "register_patient", {**jane, "first_name": "Ann"})
    assert dup.startswith("DUPLICATE_PHONE")
    assert tool_call(client, "register_patient", {**jane, "first_name": "Ann", "force_new": True}).startswith("SAVED")


def test_update_returning_patient(client, jane):
    tool_call(client, "register_patient", jane)
    pid = client.get("/patients").json()["data"][0]["patient_id"]
    out = tool_call(client, "update_patient", {"patient_id": pid, "city": "Edison", "zip_code": "08817"})
    assert out.startswith("UPDATED")
    assert client.get(f"/patients/{pid}").json()["data"]["city"] == "Edison"
    assert tool_call(client, "update_patient", {"patient_id": str(uuid.uuid4()), "city": "X"}).startswith("NOT_FOUND")


def test_arguments_as_json_string_and_empty_optionals(client, jane):
    import json
    args = json.dumps({**jane, "email": "", "insurance_provider": "N/A"})
    assert tool_call(client, "register_patient", args).startswith("SAVED")


def test_database_failure_is_spoken_not_silent(client, jane, monkeypatch):
    from sqlalchemy.exc import OperationalError
    from app.services import patients as svc

    def boom(*a, **k):
        raise OperationalError("insert", {}, Exception("db down"))

    monkeypatch.setattr(svc, "create_patient", boom)
    assert tool_call(client, "register_patient", jane).startswith("SYSTEM_ERROR")


def test_end_of_call_report_stores_transcript(client, jane):
    tool_call(client, "register_patient", jane, call_id="call-9")
    r = client.post("/vapi/webhook", json={"message": {
        "type": "end-of-call-report", "endedReason": "assistant-ended-call",
        "call": {"id": "call-9", "customer": {"number": "+17325550123"}},
        "artifact": {"transcript": "AI: Hi! User: I'm Jane."}, "analysis": {"summary": "Jane registered."},
    }})
    assert r.status_code == 200
    pid = client.get("/patients").json()["data"][0]["patient_id"]
    page = client.get(f"/dashboard/{pid}")
    assert "I&#x27;m Jane" in page.text and "Jane registered." in page.text


def test_unknown_tool_and_other_events(client):
    assert tool_call(client, "nope", {}).startswith("UNKNOWN_TOOL")
    assert client.post("/vapi/webhook", json={"message": {"type": "status-update"}}).json() == {"ok": True}


def test_secret_is_enforced_when_configured(client, monkeypatch):
    from app.api import vapi
    monkeypatch.setattr(vapi, "VAPI_SECRET", "s3cret")
    msg = {"message": {"type": "status-update"}}
    assert client.post("/vapi/webhook", json=msg).status_code == 401
    assert client.post("/vapi/webhook", json=msg, headers={"X-Vapi-Secret": "s3cret"}).status_code == 200
