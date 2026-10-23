"""Fonasa Modalidad Libre Elección (MLE) tariff for laboratory exams (group 03), taken from Fonasa's
"Libro Arancel MLE 2026". A Fonasa patient pays the copay of the lab's agreement level; Fonasa pays the rest.
Prestaciones with a single value in the book cost the same at every level."""
import csv
import re
from functools import cache
from pathlib import Path

TARIFF_FILE = Path(__file__).parent / "data" / "fonasa_mle_2026.csv"
TARIFF_YEAR = 2026


@cache
def tariff():
    with TARIFF_FILE.open(newline="") as fh:
        return {row["code"]: row for row in csv.DictReader(fh)}


def parse_codes(text):
    """[(code, quantity)] from an exam's fonasa_code, for example "0302100 0302101" or "0302032x3"."""
    items = []
    for token in re.split(r"[\s+,;]+", text.strip()):
        match = re.fullmatch(r"(\d{2})-?(\d{2})-?(\d{3})(?:[x*](\d+))?", token, re.IGNORECASE)
        if match:
            items.append(("".join(match.groups()[:3]), int(match.group(4) or 1)))
    return items


def copay(codes, level):
    """What a Fonasa patient pays for an exam at a lab of that level, or None if a code isn't in the tariff."""
    items = parse_codes(codes or "")
    if not items or level not in (1, 2, 3):
        return None
    total = 0
    for code, quantity in items:
        row = tariff().get(code)
        if row is None:
            return None
        total += int(row[f"copay_{level}"]) * quantity
    return total
