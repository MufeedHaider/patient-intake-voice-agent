"""REST API for patient records. Every response uses {"data": ..., "error": ...}."""
import uuid

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.db import get_session
from app.schemas import PatientCreate, PatientOut, PatientUpdate, envelope
from app.services import patients as svc

router = APIRouter(prefix="/patients", tags=["patients"])


def _error(status: int, code: str, message: str, details=None) -> JSONResponse:
    return JSONResponse(status_code=status, content=envelope(error={"code": code, "message": message, "details": details}))


def _out(patient) -> dict:
    return PatientOut.model_validate(patient).model_dump(mode="json")


def _parse_id(patient_id: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(patient_id)
    except ValueError:
        return None


@router.get("")
def list_patients(
    last_name: str | None = Query(None, max_length=50),
    date_of_birth: str | None = Query(None, description="MM/DD/YYYY or YYYY-MM-DD"),
    phone_number: str | None = Query(None),
    db: Session = Depends(get_session),
):
    try:
        rows = svc.list_patients(db, last_name, date_of_birth, phone_number)
    except ValueError as exc:
        return _error(400, "bad_request", str(exc))
    return envelope([_out(p) for p in rows])


@router.get("/{patient_id}")
def get_patient(patient_id: str, db: Session = Depends(get_session)):
    pid = _parse_id(patient_id)
    if pid is None:
        return _error(400, "bad_request", "patient_id must be a valid UUID")
    try:
        return envelope(_out(svc.get_patient(db, pid)))
    except svc.NotFound as exc:
        return _error(404, "not_found", str(exc))


@router.post("", status_code=201)
def create_patient(body: PatientCreate, db: Session = Depends(get_session)):
    return envelope(_out(svc.create_patient(db, body)))


@router.put("/{patient_id}")
def update_patient(patient_id: str, body: PatientUpdate, db: Session = Depends(get_session)):
    pid = _parse_id(patient_id)
    if pid is None:
        return _error(400, "bad_request", "patient_id must be a valid UUID")
    try:
        return envelope(_out(svc.update_patient(db, pid, body)))
    except svc.NotFound as exc:
        return _error(404, "not_found", str(exc))
    except svc.InvalidUpdate as exc:
        return _error(422, "validation_error", str(exc))


@router.delete("/{patient_id}")
def delete_patient(patient_id: str, db: Session = Depends(get_session)):
    pid = _parse_id(patient_id)
    if pid is None:
        return _error(400, "bad_request", "patient_id must be a valid UUID")
    try:
        patient = svc.soft_delete_patient(db, pid)
    except svc.NotFound as exc:
        return _error(404, "not_found", str(exc))
    return envelope({"patient_id": str(patient.patient_id), "deleted_at": patient.deleted_at.isoformat()})
