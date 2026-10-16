from dataclasses import dataclass

from rapidfuzz import fuzz

from .matching import DIGITS_RE, normalize

_FUZZY_MIN = 80


@dataclass
class Suggestion:
    exam: object
    alias: str = ""


def _rank(query, exam):
    name = normalize(exam.name)
    synonyms = [(normalize(s), s) for s in exam.synonym_list]
    if query == name:
        return -1, ""
    for key, original in synonyms:
        if query == key:
            return -1, original
    if name.startswith(query):
        return 0, ""
    if any(word.startswith(query) for word in name.split()):
        return 1, ""
    for key, original in synonyms:
        if key.startswith(query) or any(word.startswith(query) for word in key.split()):
            return 2, original
    if query in name:
        return 3, ""
    for key, original in synonyms:
        if query in key:
            return 4, original
    if len(query) >= 3:
        query_digits = set(DIGITS_RE.findall(query))
        best, best_alias = 0, ""
        for key, original in [(name, ""), *synonyms]:
            if not query_digits <= set(DIGITS_RE.findall(key)):
                continue
            score = fuzz.WRatio(query, key)
            if score > best:
                best, best_alias = score, original
        if best >= _FUZZY_MIN:
            return 5 + (100 - best) / 100, best_alias
    return None, ""


def suggest_exams(exams, text, limit=8):
    query = normalize(text)
    if not query:
        return []
    ranked = []
    for exam in exams:
        rank, alias = _rank(query, exam)
        if rank is not None:
            ranked.append((rank, exam.name, Suggestion(exam, alias)))
    ranked.sort(key=lambda item: (item[0], item[1]))
    return [suggestion for _, _, suggestion in ranked[:limit]]
