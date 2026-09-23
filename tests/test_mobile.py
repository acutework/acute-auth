import pytest

from app.core.errors import InvalidMobile
from app.core.mobile import normalise_mobile


@pytest.mark.parametrize(
    "raw",
    ["919999999999", "+919999999999", " +91 99999 99999 ", "+91-99999-99999"],
)
def test_accepted_forms_all_normalise_to_digits(raw):
    assert normalise_mobile(raw) == "919999999999"


@pytest.mark.parametrize("raw", ["", "abc", "0919999999999", "12345", "9" * 20])
def test_unusable_numbers_are_rejected(raw):
    with pytest.raises(InvalidMobile):
        normalise_mobile(raw)
