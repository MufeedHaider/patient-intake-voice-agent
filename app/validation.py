"""Field normalizers and validators shared by the REST API and the voice agent.

Every function takes raw input (as typed into the API or as heard on the phone),
returns a clean value, or raises ValueError with a message short enough for the
voice agent to read back to the caller.
"""
import re
from datetime import date, datetime, timezone

US_STATES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California",
    "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware", "FL": "Florida", "GA": "Georgia",
    "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois", "IN": "Indiana", "IA": "Iowa",
    "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi",
    "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada", "NH": "New Hampshire",
    "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York", "NC": "North Carolina",
    "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma", "OR": "Oregon", "PA": "Pennsylvania",
    "RI": "Rhode Island", "SC": "South Carolina", "SD": "South Dakota", "TN": "Tennessee",
    "TX": "Texas", "UT": "Utah", "VT": "Vermont", "VA": "Virginia", "WA": "Washington",
    "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming", "DC": "District of Columbia",
    "PR": "Puerto Rico", "GU": "Guam", "VI": "U.S. Virgin Islands", "AS": "American Samoa",
    "MP": "Northern Mariana Islands",
}
_STATE_BY_NAME = {name.lower(): code for code, name in US_STATES.items()}

SEX_OPTIONS = {
    "male": "Male", "m": "Male", "man": "Male",
    "female": "Female", "f": "Female", "woman": "Female",
    "other": "Other", "non-binary": "Other", "nonbinary": "Other",
    "decline to answer": "Decline to Answer", "decline": "Decline to Answer",
    "prefer not to say": "Decline to Answer", "prefer not to answer": "Decline to Answer",
}

# Letters, then letters / hyphens / apostrophes, with single spaces allowed
# between parts (e.g. "Mary Ann", "O'Brien", "Smith-Jones").
_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z'\-]*( [A-Za-z][A-Za-z'\-]*)*$")
_ZIP_RE = re.compile(r"^\d{5}(-\d{4})?$")
_MEMBER_ID_RE = re.compile(r"^[A-Za-z0-9\-]{1,50}$")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")


def clean_text(value: str | None) -> str | None:
    """Trim whitespace and strip control characters (basic input sanitization)."""
    if value is None:
        return None
    value = re.sub(r"[\x00-\x1f\x7f]", "", str(value))
    value = re.sub(r"\s+", " ", value).strip()
    return value or None


def normalize_name(value: str, label: str = "name") -> str:
    value = clean_text(value) or ""
    if not 1 <= len(value) <= 50:
        raise ValueError(f"{label} must be 1 to 50 characters")
    if not _NAME_RE.match(value):
        raise ValueError(f"{label} can only contain letters, hyphens and apostrophes")
    return value


def normalize_dob(value) -> date:
    """Accepts MM/DD/YYYY (preferred), YYYY-MM-DD, or a date object."""
    if isinstance(value, datetime):
        value = value.date()
    if isinstance(value, date):
        parsed = value
    else:
        text = clean_text(str(value)) or ""
        parsed = None
        for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m-%d-%Y"):
            try:
                parsed = datetime.strptime(text, fmt).date()
                break
            except ValueError:
                continue
        if parsed is None:
            raise ValueError("date of birth must be a real date in MM/DD/YYYY format")
    today = datetime.now(timezone.utc).date()
    if parsed > today:
        raise ValueError("date of birth cannot be in the future")
    if parsed.year < 1900:
        raise ValueError("date of birth must be after 1900")
    return parsed


def normalize_sex(value: str) -> str:
    key = (clean_text(value) or "").lower()
    if key not in SEX_OPTIONS:
        raise ValueError("sex must be Male, Female, Other, or Decline to Answer")
    return SEX_OPTIONS[key]


def normalize_phone(value: str, label: str = "phone number") -> str:
    digits = re.sub(r"\D", "", str(value or ""))
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) != 10:
        raise ValueError(f"{label} must be a 10-digit U.S. number")
    if digits[0] in "01":
        # U.S. area codes never start with 0 or 1.
        raise ValueError(f"{label} has an invalid area code")
    return digits


def normalize_email(value: str | None) -> str | None:
    value = clean_text(value)
    if value is None:
        return None
    value = value.replace(" at ", "@").replace(" dot ", ".").replace(" ", "").lower()
    if len(value) > 254 or not _EMAIL_RE.match(value):
        raise ValueError("email address is not valid")
    return value


def normalize_state(value: str) -> str:
    text = clean_text(value) or ""
    code = text.upper().replace(".", "")
    if code in US_STATES:
        return code
    if text.lower() in _STATE_BY_NAME:
        return _STATE_BY_NAME[text.lower()]
    raise ValueError("state must be a valid U.S. state")


def normalize_zip(value: str) -> str:
    text = re.sub(r"\s", "", str(value or ""))
    if re.fullmatch(r"\d{9}", text):
        text = f"{text[:5]}-{text[5:]}"
    if not _ZIP_RE.match(text):
        raise ValueError("ZIP code must be 5 digits or ZIP+4")
    return text


def normalize_city(value: str) -> str:
    value = clean_text(value) or ""
    if not 1 <= len(value) <= 100:
        raise ValueError("city must be 1 to 100 characters")
    return value


def normalize_required_text(value: str | None, label: str, max_len: int) -> str:
    value = clean_text(value) or ""
    if not value:
        raise ValueError(f"{label} is required")
    if len(value) > max_len:
        raise ValueError(f"{label} must be at most {max_len} characters")
    return value


def normalize_optional_text(value: str | None, label: str, max_len: int) -> str | None:
    value = clean_text(value)
    if value and len(value) > max_len:
        raise ValueError(f"{label} must be at most {max_len} characters")
    return value


def normalize_member_id(value: str | None) -> str | None:
    value = clean_text(value)
    if value is None:
        return None
    value = value.replace(" ", "")
    if not _MEMBER_ID_RE.match(value):
        raise ValueError("insurance member ID must be letters and numbers only")
    return value.upper()


def format_dob(value: date) -> str:
    return value.strftime("%m/%d/%Y")
