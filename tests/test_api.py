"""REST API: CRUD, filters, soft delete, validation and the response envelope."""


def create(client, body):
    r = client.post("/patients", json=body)
    assert r.status_code == 201, r.text
    return r.json()["data"]


def test_create_normalizes_and_returns_envelope(client, jane):
    r = client.post("/patients", json=jane)
    assert r.status_code == 201
    body = r.json()
    assert body["error"] is None
    p = body["data"]
    assert p["patient_id"]
    assert p["phone_number"] == "7325550123"
    assert p["state"] == "NJ"
    assert p["sex"] == "Female"
    assert p["date_of_birth"] == "04/12/1988"
    assert p["preferred_language"] == "English"


def test_invalid_fields_return_422_with_field_details(client, jane):
    bad = {**jane, "date_of_birth": "01/01/2999", "phone_number": "555", "state": "ZZ", "zip_code": "123"}
    r = client.post("/patients", json=bad)
    assert r.status_code == 422
    fields = {d["field"] for d in r.json()["error"]["details"]}
    assert {"date_of_birth", "phone_number", "state", "zip_code"} <= fields
    assert r.json()["data"] is None


def test_missing_required_field_is_rejected(client, jane):
    body = dict(jane)
    del body["city"]
    assert client.post("/patients", json=body).status_code == 422


def test_get_and_404_and_bad_uuid(client, jane):
    p = create(client, jane)
    assert client.get(f"/patients/{p['patient_id']}").json()["data"]["first_name"] == "Jane"
    assert client.get("/patients/00000000-0000-0000-0000-000000000000").status_code == 404
    assert client.get("/patients/not-a-uuid").status_code == 400


def test_list_filters(client, jane):
    create(client, jane)
    create(client, {**jane, "first_name": "Bob", "last_name": "Davis", "phone_number": "2125550147",
                    "date_of_birth": "1990-03-04"})
    assert len(client.get("/patients").json()["data"]) == 2
    assert len(client.get("/patients", params={"last_name": "davis"}).json()["data"]) == 1
    assert len(client.get("/patients", params={"date_of_birth": "03/04/1990"}).json()["data"]) == 1
    assert len(client.get("/patients", params={"phone_number": "732-555-0123"}).json()["data"]) == 1
    assert client.get("/patients", params={"date_of_birth": "nonsense"}).status_code == 400


def test_partial_update(client, jane):
    p = create(client, jane)
    r = client.put(f"/patients/{p['patient_id']}", json={"last_name": "Davis", "email": "Jane@Example.com"})
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["last_name"] == "Davis" and data["email"] == "jane@example.com"
    assert data["city"] == "Somerset"  # untouched
    assert data["updated_at"] >= data["created_at"]


def test_update_cannot_blank_required_field(client, jane):
    p = create(client, jane)
    r = client.put(f"/patients/{p['patient_id']}", json={"city": None})
    assert r.status_code == 422


def test_soft_delete_hides_record_but_keeps_row(client, jane):
    from app.db import SessionLocal
    from app.models import Patient

    p = create(client, jane)
    r = client.delete(f"/patients/{p['patient_id']}")
    assert r.status_code == 200 and r.json()["data"]["deleted_at"]
    assert client.get(f"/patients/{p['patient_id']}").status_code == 404
    assert client.get("/patients").json()["data"] == []
    with SessionLocal() as db:  # the row is still in the database
        assert db.query(Patient).count() == 1


def test_unknown_field_rejected(client, jane):
    assert client.post("/patients", json={**jane, "ssn": "123"}).status_code == 422


def test_dashboard_and_health(client, jane):
    create(client, jane)
    assert client.get("/health").json()["data"]["status"] == "ok"
    page = client.get("/dashboard")
    assert page.status_code == 200 and "O&#x27;Neil-Smith" in page.text
