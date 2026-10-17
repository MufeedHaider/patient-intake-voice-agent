"""A small read-only web dashboard of registered patients and their call transcripts."""
import uuid
from html import escape

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app import validation as v
from app.db import get_session
from app.services import patients as svc

router = APIRouter(tags=["dashboard"])

_STYLE = """
<style>
  :root { --bg:#f7f8fa; --card:#fff; --ink:#1d2433; --muted:#5b6578; --line:#e3e7ee; --accent:#1f6feb; }
  @media (prefers-color-scheme: dark) { :root { --bg:#0f141b; --card:#161d27; --ink:#e6ebf2; --muted:#9aa6b8; --line:#273142; --accent:#58a6ff; } }
  * { box-sizing:border-box; }
  body { margin:0; font:15px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif; background:var(--bg); color:var(--ink); }
  main { max-width:1200px; margin:0 auto; padding:24px 16px; }
  h1 { font-size:22px; margin:0 0 4px; } p.sub { color:var(--muted); margin:0 0 20px; }
  .card { background:var(--card); border:1px solid var(--line); border-radius:10px; overflow-x:auto; }
  table { width:100%; border-collapse:collapse; }
  th, td { text-align:left; padding:10px 12px; border-bottom:1px solid var(--line); white-space:nowrap; }
  th { font-size:12px; text-transform:uppercase; letter-spacing:.04em; color:var(--muted); }
  a { color:var(--accent); text-decoration:none; } a:hover { text-decoration:underline; }
  pre { white-space:pre-wrap; background:var(--bg); border:1px solid var(--line); border-radius:8px; padding:12px; }
  dl { display:grid; grid-template-columns:200px 1fr; gap:6px 16px; padding:16px; margin:0; }
  dt { color:var(--muted); }
</style>
"""


def _page(title: str, body: str) -> HTMLResponse:
    return HTMLResponse(
        f"<!doctype html><html><head><meta charset='utf-8'>"
        f"<meta name='viewport' content='width=device-width,initial-scale=1'><title>{escape(title)}</title>"
        f"{_STYLE}</head><body><main>{body}</main></body></html>"
    )


def _phone(p: str | None) -> str:
    return f"({p[:3]}) {p[3:6]}-{p[6:]}" if p and len(p) == 10 else (p or "")


@router.get("/", response_class=HTMLResponse)
@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(db: Session = Depends(get_session)):
    rows = svc.list_patients(db)
    trs = "".join(
        f"<tr><td><a href='/dashboard/{p.patient_id}'>{escape(p.first_name)} {escape(p.last_name)}</a></td>"
        f"<td>{v.format_dob(p.date_of_birth)}</td><td>{escape(p.sex)}</td><td>{_phone(p.phone_number)}</td>"
        f"<td>{escape(p.city)}, {escape(p.state)}</td><td>{escape(p.insurance_provider or '')}</td>"
        f"<td>{p.created_at:%Y-%m-%d %H:%M} UTC</td></tr>"
        for p in rows
    ) or "<tr><td colspan='7'>No patients yet. Call the number to register one.</td></tr>"
    body = (
        "<h1>Patient registrations</h1>"
        f"<p class='sub'>{len(rows)} active patient(s). Data comes live from the database. "
        "API docs: <a href='/docs'>/docs</a></p>"
        "<div class='card'><table><thead><tr><th>Name</th><th>Date of birth</th><th>Sex</th><th>Phone</th>"
        "<th>City</th><th>Insurance</th><th>Registered</th></tr></thead>"
        f"<tbody>{trs}</tbody></table></div>"
    )
    return _page("Patient registrations", body)


@router.get("/dashboard/{patient_id}", response_class=HTMLResponse)
def patient_detail(patient_id: str, db: Session = Depends(get_session)):
    try:
        p = svc.get_patient(db, uuid.UUID(patient_id))
    except (ValueError, svc.NotFound):
        return _page("Not found", "<h1>Patient not found</h1><p><a href='/dashboard'>Back</a></p>")
    fields = [
        ("Patient ID", str(p.patient_id)), ("Name", f"{p.first_name} {p.last_name}"),
        ("Date of birth", v.format_dob(p.date_of_birth)), ("Sex", p.sex), ("Phone", _phone(p.phone_number)),
        ("Email", p.email), ("Address", ", ".join(x for x in [p.address_line_1, p.address_line_2] if x)),
        ("City / State / ZIP", f"{p.city}, {p.state} {p.zip_code}"),
        ("Insurance", " / ".join(x for x in [p.insurance_provider, p.insurance_member_id] if x)),
        ("Preferred language", p.preferred_language),
        ("Emergency contact", " / ".join(x for x in [p.emergency_contact_name, _phone(p.emergency_contact_phone)] if x)),
        ("Created", f"{p.created_at:%Y-%m-%d %H:%M} UTC"), ("Updated", f"{p.updated_at:%Y-%m-%d %H:%M} UTC"),
    ]
    dl = "".join(f"<dt>{escape(k)}</dt><dd>{escape(val or '—')}</dd>" for k, val in fields)
    calls = svc.calls_for_patient(db, p.patient_id)
    call_html = "".join(
        f"<h3>Call {escape(c.call_id)} · {c.created_at:%Y-%m-%d %H:%M} UTC</h3>"
        f"<p>{escape(c.summary or '')}</p><pre>{escape(c.transcript or 'Transcript not received yet.')}</pre>"
        for c in calls
    ) or "<p class='sub'>No call transcripts linked to this patient.</p>"
    body = (
        "<p><a href='/dashboard'>← All patients</a></p>"
        f"<h1>{escape(p.first_name)} {escape(p.last_name)}</h1>"
        f"<div class='card'><dl>{dl}</dl></div><h2>Calls</h2>{call_html}"
    )
    return _page(f"{p.first_name} {p.last_name}", body)
