import re

_CLEAN_RE = re.compile(r"[^0-9kK]")


def check_digit(number):
    total, factor = 0, 2
    for digit in reversed(str(number)):
        total += int(digit) * factor
        factor = 2 if factor == 7 else factor + 1
    remainder = 11 - total % 11
    return {11: "0", 10: "K"}.get(remainder, str(remainder))


def format_rut(text):
    """Returns the RUT as 12.345.678-5, or "" when it's missing or the check digit is wrong."""
    clean = _CLEAN_RE.sub("", text or "").upper()
    if len(clean) < 2 or not clean[:-1].isdigit():
        return ""
    number, digit = clean[:-1], clean[-1]
    if check_digit(number) != digit:
        return ""
    return f"{int(number):,}".replace(",", ".") + f"-{digit}"
