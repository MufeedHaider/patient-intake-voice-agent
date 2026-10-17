"""Database tables.

The schema enforces the data model with column types, lengths, NOT NULL and
CHECK constraints. Format rules that need regular expressions (names, ZIP,
email) are enforced in app/validation.py, before anything reaches the database,
so they behave the same on SQLite and PostgreSQL.
"""
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

SEX_VALUES = ("Male", "Female", "Other", "Decline to Answer")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Patient(Base):
    __tablename__ = "patients"

    patient_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)

    first_name: Mapped[str] = mapped_column(String(50), nullable=False)
    last_name: Mapped[str] = mapped_column(String(50), nullable=False)
    date_of_birth: Mapped[date] = mapped_column(Date, nullable=False)
    sex: Mapped[str] = mapped_column(String(20), nullable=False)
    phone_number: Mapped[str] = mapped_column(String(10), nullable=False)
    email: Mapped[str | None] = mapped_column(String(254))
    address_line_1: Mapped[str] = mapped_column(String(200), nullable=False)
    address_line_2: Mapped[str | None] = mapped_column(String(200))
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    state: Mapped[str] = mapped_column(String(2), nullable=False)
    zip_code: Mapped[str] = mapped_column(String(10), nullable=False)
    insurance_provider: Mapped[str | None] = mapped_column(String(100))
    insurance_member_id: Mapped[str | None] = mapped_column(String(50))
    preferred_language: Mapped[str] = mapped_column(String(50), nullable=False, default="English")
    emergency_contact_name: Mapped[str | None] = mapped_column(String(100))
    emergency_contact_phone: Mapped[str | None] = mapped_column(String(10))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint(f"sex IN {SEX_VALUES}", name="ck_patients_sex"),
        CheckConstraint("length(first_name) BETWEEN 1 AND 50", name="ck_patients_first_name_len"),
        CheckConstraint("length(last_name) BETWEEN 1 AND 50", name="ck_patients_last_name_len"),
        CheckConstraint("length(phone_number) = 10", name="ck_patients_phone_len"),
        CheckConstraint("length(state) = 2", name="ck_patients_state_len"),
        CheckConstraint("length(city) BETWEEN 1 AND 100", name="ck_patients_city_len"),
        Index("ix_patients_phone_number", "phone_number"),
        Index("ix_patients_last_name", "last_name"),
        Index("ix_patients_date_of_birth", "date_of_birth"),
    )


class CallLog(Base):
    """One row per phone call: transcript and summary from Vapi's end-of-call report."""

    __tablename__ = "call_logs"

    call_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    patient_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("patients.patient_id"))
    caller_number: Mapped[str | None] = mapped_column(String(20))
    ended_reason: Mapped[str | None] = mapped_column(String(100))
    summary: Mapped[str | None] = mapped_column(Text)
    transcript: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )
