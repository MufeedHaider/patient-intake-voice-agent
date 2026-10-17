"""Webhook that Vapi calls during and after each phone call.

Vapi handles telephony, speech-to-text, text-to-speech and the LLM. When the LLM
decides to use one of our tools, Vapi POSTs a "tool-calls" message here. We run
the tool against the same service layer the REST API uses and return a short
plain-English result that the LLM turns into speech.

Vapi rules we follow (docs.vapi.ai/tools/custom-tools):
  * always answer HTTP 200, even when a tool fails;
  * return one {"toolCallId", "result"} entry per tool call;
  * results are flat strings.
"""
import json
import logging
import uuid
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app import validation as v
from app.config import VAPI_SECRET
from app.db import get_session
from app.schemas import PatientCreate, PatientUpdate
from app.services import patients as svc

log = logging.getLogger("vapi")
router = APIRouter(prefix="/vapi", tags=["voice agent"])

SYSTEM_ERROR = (
    "SYSTEM_ERROR: the record could not be saved because of a technical problem. "
    "Apologise, tell the caller their information was not saved, and suggest calling back later."
)


def _authorized(request: Request) -> bool:
    if not VAPI_SECRET:
        return True
    header = request.headers.get("x-vapi-secret", "")
    bearer = request.headers.get("authorization", "")
    return header == VAPI_SECRET or bearer == f"Bearer {VAPI_SECRET}"


def _args(raw: Any) -> dict:
    """Vapi normally sends arguments as an object; accept a JSON string too."""
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}
    return {}


def _drop_empty(args: dict) -> dict:
    """The LLM sometimes sends "" or "N/A" for fields the caller skipped."""
    empty = {"", "none", "n/a", "na", "null", "not provided", "unknown"}
    return {k: val for k, val in args.items() if not (isinstance(val, str) and val.strip().lower() in empty)}


def _validation_feedback(exc: ValidationError) -> str:
    problems = []
    for err in exc.errors():
        field = str(err["loc"][0]) if err.get("loc") else "input"
        if err["type"] == "missing":
            problems.append(f"{field}: missing")
        elif err["type"] == "extra_forbidden":
            continue
        else:
            problems.append(f"{field}: {err['msg'].removeprefix('Value error, ')}")
    return (
        "NOT_SAVED. Fix these fields, then call the tool again: "
        + "; ".join(problems)
        + ". Ask the caller again only for these fields, one at a time, and do not repeat fields that were fine."
    )


def _describe(p) -> str:
    return (
        f"patient_id={p.patient_id}; name={p.first_name} {p.last_name}; "
        f"date_of_birth={v.format_dob(p.date_of_birth)}; phone={p.phone_number}; "
        f"address={p.address_line_1}{', ' + p.address_line_2 if p.address_line_2 else ''}, "
        f"{p.city}, {p.state} {p.zip_code}"
    )


# --- tools -----------------------------------------------------------------

def tool_find_patient_by_phone(db: Session, args: dict, call_id: str | None) -> str:
    try:
        matches = svc.find_by_phone(db, args.get("phone_number", ""))
    except ValueError as exc:
        return f"INVALID_PHONE: {exc}. Ask the caller to repeat their 10-digit phone number."
    if not matches:
        return "NO_MATCH: no existing patient uses this phone number. Continue with a new registration."
    lines = "; ".join(_describe(p) for p in matches)
    return (
        f"MATCH_FOUND: {len(matches)} existing record(s) use this phone number: {lines}. "
        "Ask: 'It looks like we already have a record for <First Name> <Last Name>. "
        "Would you like to update your information instead?' If yes, collect only what changed and call "
        "update_patient with that patient_id. If they are a different person sharing the phone, continue the "
        "new registration and pass force_new=true to register_patient."
    )


def tool_register_patient(db: Session, args: dict, call_id: str | None) -> str:
    force_new = str(args.pop("force_new", "")).strip().lower() in {"true", "yes", "1"}
    try:
        data = PatientCreate(**_drop_empty(args))
    except ValidationError as exc:
        return _validation_feedback(exc)
    if not force_new:
        existing = svc.find_by_phone(db, data.phone_number)
        if existing:
            p = existing[0]
            return (
                f"DUPLICATE_PHONE: {p.first_name} {p.last_name} (patient_id={p.patient_id}) already uses this "
                "phone number. Ask whether they want to update that record (use update_patient) or create a "
                "separate record (call register_patient again with force_new=true)."
            )
    patient = svc.create_patient(db, data, call_id=call_id)
    log.info("registration_payload %s", json.dumps(data.model_dump(mode="json")))
    return f"SAVED: patient registered with patient_id={patient.patient_id}. Tell the caller they're all set, using their first name, then end the call."


def tool_update_patient(db: Session, args: dict, call_id: str | None) -> str:
    try:
        patient_id = uuid.UUID(str(args.pop("patient_id", "")))
    except ValueError:
        return "INVALID: patient_id is missing or not valid. Use the patient_id returned by find_patient_by_phone."
    try:
        data = PatientUpdate(**_drop_empty(args))
    except ValidationError as exc:
        return _validation_feedback(exc)
    try:
        patient = svc.update_patient(db, patient_id, data, call_id=call_id)
    except svc.NotFound:
        return "NOT_FOUND: no active patient has that patient_id."
    except svc.InvalidUpdate as exc:
        return f"NOT_SAVED: {exc}."
    log.info("update_payload patient_id=%s %s", patient_id, json.dumps(data.model_dump(mode="json", exclude_unset=True)))
    return f"UPDATED: record for {patient.first_name} {patient.last_name} updated. Confirm to the caller and end the call."


TOOLS = {
    "find_patient_by_phone": tool_find_patient_by_phone,
    "register_patient": tool_register_patient,
    "update_patient": tool_update_patient,
}


# --- webhook ---------------------------------------------------------------

@router.post("/webhook")
async def webhook(request: Request, db: Session = Depends(get_session)):
    if not _authorized(request):
        log.warning("rejected webhook call with a wrong or missing secret")
        return JSONResponse(status_code=401, content={"error": "unauthorized"})

    body = await request.json()
    message = body.get("message", {}) or {}
    kind = message.get("type")
    call = message.get("call") or {}
    call_id = call.get("id")

    if kind == "tool-calls":
        results = []
        for tc in message.get("toolCallList") or []:
            fn = tc.get("function") or {}
            name, args = fn.get("name"), _args(fn.get("arguments"))
            log.info("tool_call call_id=%s tool=%s", call_id, name)
            handler = TOOLS.get(name)
            if handler is None:
                result = f"UNKNOWN_TOOL: {name}"
            else:
                try:
                    result = handler(db, dict(args), call_id)
                except SQLAlchemyError:
                    db.rollback()
                    log.exception("database error in tool %s", name)
                    result = SYSTEM_ERROR
                except Exception:  # never leave the caller in silence
                    db.rollback()
                    log.exception("unexpected error in tool %s", name)
                    result = SYSTEM_ERROR
            log.info("tool_result call_id=%s tool=%s result=%s", call_id, name, result[:300])
            results.append({"toolCallId": tc.get("id"), "result": result})
        return {"results": results}

    if kind == "end-of-call-report" and call_id:
        artifact = message.get("artifact") or {}
        analysis = message.get("analysis") or {}
        customer = call.get("customer") or message.get("customer") or {}
        transcript = artifact.get("transcript") or message.get("transcript")
        summary = analysis.get("summary") or message.get("summary")
        try:
            svc.save_call_report(db, call_id, customer.get("number"), message.get("endedReason"), summary, transcript)
        except SQLAlchemyError:
            db.rollback()
            log.exception("could not store call report for %s", call_id)
        log.info("call_ended call_id=%s reason=%s", call_id, message.get("endedReason"))
        log.info("call_transcript call_id=%s\n%s", call_id, transcript or "(no transcript)")
        return {"ok": True}

    # status-update, conversation-update, etc. need no answer.
    return {"ok": True}
