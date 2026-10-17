"""Request and response models for the REST API.

Validation lives in app/validation.py so the API and the voice agent apply
exactly the same rules.
"""
import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, field_serializer, field_validator

from app import validation as v


class PatientBase(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    @field_validator("first_name", check_fields=False)
    @classmethod
    def _first(cls, value):
        return None if value is None else v.normalize_name(value, "first name")

    @field_validator("last_name", check_fields=False)
    @classmethod
    def _last(cls, value):
        return None if value is None else v.normalize_name(value, "last name")

    @field_validator("date_of_birth", mode="before", check_fields=False)
    @classmethod
    def _dob(cls, value):
        return None if value is None else v.normalize_dob(value)

    @field_validator("sex", check_fields=False)
    @classmethod
    def _sex(cls, value):
        return None if value is None else v.normalize_sex(value)

    @field_validator("phone_number", mode="before", check_fields=False)
    @classmethod
    def _phone(cls, value):
        return None if value is None else v.normalize_phone(value)

    @field_validator("emergency_contact_phone", mode="before", check_fields=False)
    @classmethod
    def _ec_phone(cls, value):
        if value in (None, ""):
            return None
        return v.normalize_phone(value, "emergency contact phone")

    @field_validator("email", check_fields=False)
    @classmethod
    def _email(cls, value):
        return v.normalize_email(value)

    @field_validator("address_line_1", check_fields=False)
    @classmethod
    def _addr1(cls, value):
        return None if value is None else v.normalize_required_text(value, "street address", 200)

    @field_validator("address_line_2", check_fields=False)
    @classmethod
    def _addr2(cls, value):
        return v.normalize_optional_text(value, "address line 2", 200)

    @field_validator("city", check_fields=False)
    @classmethod
    def _city(cls, value):
        return None if value is None else v.normalize_city(value)

    @field_validator("state", check_fields=False)
    @classmethod
    def _state(cls, value):
        return None if value is None else v.normalize_state(value)

    @field_validator("zip_code", mode="before", check_fields=False)
    @classmethod
    def _zip(cls, value):
        return None if value is None else v.normalize_zip(value)

    @field_validator("insurance_provider", check_fields=False)
    @classmethod
    def _insurer(cls, value):
        return v.normalize_optional_text(value, "insurance provider", 100)

    @field_validator("insurance_member_id", mode="before", check_fields=False)
    @classmethod
    def _member(cls, value):
        return v.normalize_member_id(value)

    @field_validator("preferred_language", check_fields=False)
    @classmethod
    def _language(cls, value):
        return v.normalize_optional_text(value, "preferred language", 50)

    @field_validator("emergency_contact_name", check_fields=False)
    @classmethod
    def _ec_name(cls, value):
        return v.normalize_optional_text(value, "emergency contact name", 100)


class PatientCreate(PatientBase):
    first_name: str
    last_name: str
    date_of_birth: date
    sex: str
    phone_number: str
    email: str | None = None
    address_line_1: str
    address_line_2: str | None = None
    city: str
    state: str
    zip_code: str
    insurance_provider: str | None = None
    insurance_member_id: str | None = None
    preferred_language: str | None = "English"
    emergency_contact_name: str | None = None
    emergency_contact_phone: str | None = None


class PatientUpdate(PatientBase):
    """Partial update: every field is optional; only fields sent are changed."""

    first_name: str | None = None
    last_name: str | None = None
    date_of_birth: date | None = None
    sex: str | None = None
    phone_number: str | None = None
    email: str | None = None
    address_line_1: str | None = None
    address_line_2: str | None = None
    city: str | None = None
    state: str | None = None
    zip_code: str | None = None
    insurance_provider: str | None = None
    insurance_member_id: str | None = None
    preferred_language: str | None = None
    emergency_contact_name: str | None = None
    emergency_contact_phone: str | None = None


class PatientOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    patient_id: uuid.UUID
    first_name: str
    last_name: str
    date_of_birth: date
    sex: str
    phone_number: str
    email: str | None
    address_line_1: str
    address_line_2: str | None
    city: str
    state: str
    zip_code: str
    insurance_provider: str | None
    insurance_member_id: str | None
    preferred_language: str
    emergency_contact_name: str | None
    emergency_contact_phone: str | None
    created_at: datetime
    updated_at: datetime

    @field_serializer("date_of_birth")
    def _dob_out(self, value: date) -> str:
        return v.format_dob(value)


def envelope(data: Any = None, error: Any = None) -> dict:
    """Every response uses the same shape: {"data": ..., "error": ...}."""
    return {"data": data, "error": error}
