"""Service layer: the only code that reads or writes patient records.

Both the REST API (app/api/patients.py) and the voice agent webhook
(app/api/vapi.py) call these functions, so validation and persistence rules
live in one place.
"""
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import validation as v
from app.models import CallLog, Patient
from app.schemas import PatientCreate, PatientUpdate

log = logging.getLogger("patients")

REQUIRED_FIELDS = (
    "first_name", "last_name", "date_of_birth", "sex", "phone_number",
    "address_line_1", "city", "state", "zip_code",
)


class NotFound(Exception):
    pass


class InvalidUpdate(ValueError):
    pass


def _active():
    return select(Patient).where(Patient.deleted_at.is_(None))


def create_patient(db: Session, data: PatientCreate, call_id: str | None = None) -> Patient:
    values = data.model_dump()
    values["preferred_language"] = values.get("preferred_language") or "English"
    patient = Patient(**values)
    db.add(patient)
    db.commit()
    db.refresh(patient)
    if call_id:
        link_call(db, call_id, patient.patient_id)
    log.info("patient_created patient_id=%s call_id=%s", patient.patient_id, call_id)
    return patient


def get_patient(db: Session, patient_id: uuid.UUID) -> Patient:
    patient = db.scalar(_active().where(Patient.patient_id == patient_id))
    if patient is None:
        raise NotFound(f"patient {patient_id} not found")
    return patient


def list_patients(
    db: Session,
    last_name: str | None = None,
    date_of_birth: str | None = None,
    phone_number: str | None = None,
) -> list[Patient]:
    query = _active()
    if last_name:
        query = query.where(func.lower(Patient.last_name) == last_name.strip().lower())
    if date_of_birth:
        query = query.where(Patient.date_of_birth == v.normalize_dob(date_of_birth))
    if phone_number:
        query = query.where(Patient.phone_number == v.normalize_phone(phone_number))
    return list(db.scalars(query.order_by(Patient.created_at.desc())))


def find_by_phone(db: Session, phone_number: str) -> list[Patient]:
    phone = v.normalize_phone(phone_number)
    return list(db.scalars(_active().where(Patient.phone_number == phone).order_by(Patient.created_at)))


def update_patient(
    db: Session, patient_id: uuid.UUID, data: PatientUpdate, call_id: str | None = None
) -> Patient:
    patient = get_patient(db, patient_id)
    changes = data.model_dump(exclude_unset=True)
    nulled = [name for name in REQUIRED_FIELDS if name in changes and changes[name] is None]
    if nulled:
        raise InvalidUpdate(f"required fields cannot be empty: {', '.join(nulled)}")
    if "preferred_language" in changes and not changes["preferred_language"]:
        changes["preferred_language"] = "English"
    for name, value in changes.items():
        setattr(patient, name, value)
    patient.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(patient)
    if call_id:
        link_call(db, call_id, patient.patient_id)
    log.info("patient_updated patient_id=%s fields=%s", patient_id, sorted(changes))
    return patient


def soft_delete_patient(db: Session, patient_id: uuid.UUID) -> Patient:
    patient = get_patient(db, patient_id)
    patient.deleted_at = datetime.now(timezone.utc)
    db.commit()
    log.info("patient_soft_deleted patient_id=%s", patient_id)
    return patient


def link_call(db: Session, call_id: str, patient_id: uuid.UUID) -> None:
    """Remember which patient a phone call created or updated."""
    call = db.get(CallLog, call_id) or CallLog(call_id=call_id)
    call.patient_id = patient_id
    db.add(call)
    db.commit()


def save_call_report(
    db: Session,
    call_id: str,
    caller_number: str | None,
    ended_reason: str | None,
    summary: str | None,
    transcript: str | None,
) -> CallLog:
    call = db.get(CallLog, call_id) or CallLog(call_id=call_id)
    call.caller_number = caller_number
    call.ended_reason = ended_reason
    call.summary = summary
    call.transcript = transcript
    db.add(call)
    db.commit()
    return call


def calls_for_patient(db: Session, patient_id: uuid.UUID) -> list[CallLog]:
    return list(
        db.scalars(select(CallLog).where(CallLog.patient_id == patient_id).order_by(CallLog.created_at.desc()))
    )


def seed(db: Session) -> None:
    """Two demo patients so the API and dashboard are not empty on first visit."""
    if db.scalar(select(func.count()).select_from(Patient)):
        return
    demo = [
        PatientCreate(
            first_name="Jane", last_name="Doe", date_of_birth="04/12/1988", sex="Female",
            phone_number="2125550147", email="jane.doe@example.com",
            address_line_1="350 5th Ave", address_line_2="Apt 12B", city="New York",
            state="NY", zip_code="10118", insurance_provider="Aetna",
            insurance_member_id="AET123456789", preferred_language="English",
            emergency_contact_name="John Doe", emergency_contact_phone="2125550199",
        ),
        PatientCreate(
            first_name="Carlos", last_name="Rivera", date_of_birth="11/03/1975", sex="Male",
            phone_number="7325550123", address_line_1="7 Clyde Rd", city="Somerset",
            state="NJ", zip_code="08873", preferred_language="Spanish",
        ),
    ]
    for item in demo:
        create_patient(db, item)
    log.info("seeded %d demo patients", len(demo))
