"""Canonical mobile number format.

Digits only, country code first, no '+' and no leading zero - the same form
acute-api uses, so both services key the same person identically. It is also
exactly what MSG91 expects on the wire.
"""

import re

from app.core.errors import InvalidMobile

_CANONICAL = re.compile(r"^[1-9]\d{10,14}$")


def normalise_mobile(value: str) -> str:
    """'+91 99999 99999' -> '919999999999'. Raises InvalidMobile if it can't be."""
    digits = re.sub(r"[\s\-()]", "", value.strip()).removeprefix("+")
    if not _CANONICAL.match(digits):
        raise InvalidMobile(
            "mobile must be <countrycode><number>: digits only, no '+', no leading 0"
        )
    return digits
