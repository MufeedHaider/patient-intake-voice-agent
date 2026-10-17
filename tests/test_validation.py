import pytest
from app import validation as v


@pytest.mark.parametrize("raw,expected", [("(732) 555-0123", "7325550123"), ("+1 732 555 0123", "7325550123")])
def test_phone_ok(raw, expected):
    assert v.normalize_phone(raw) == expected


@pytest.mark.parametrize("raw", ["555", "123-456-7890", "73255501234"])
def test_phone_bad(raw):
    with pytest.raises(ValueError):
        v.normalize_phone(raw)


def test_names():
    assert v.normalize_name("  mary  ann ") == "mary ann"
    with pytest.raises(ValueError):
        v.normalize_name("R2D2")


def test_dob_formats():
    assert v.format_dob(v.normalize_dob("1990-03-04")) == "03/04/1990"
    for bad in ("02/30/1990", "13/01/1990", "01/01/2999"):
        with pytest.raises(ValueError):
            v.normalize_dob(bad)


def test_state_zip_sex_email():
    assert v.normalize_state("new york") == "NY" and v.normalize_state("tx") == "TX"
    assert v.normalize_zip("088731234") == "08873-1234"
    assert v.normalize_sex("prefer not to say") == "Decline to Answer"
    assert v.normalize_email("John.Smith at gmail dot com") == "john.smith@gmail.com"
