import re
import unicodedata
from dataclasses import dataclass, field

from rapidfuzz import fuzz, process

MATCHER_VERSION = "fuzzy-v1"

_SPLIT_RE = re.compile(r"\s*[+,;\n]\s*")
_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")
DIGITS_RE = re.compile(r"\d+")
_SHORT_QUERY = 4
_DIGIT_MISMATCH_CAP = 0.7


def normalize(text):
    text = unicodedata.normalize("NFKD", text.replace(".", ""))
    text = "".join(c for c in text if not unicodedata.combining(c))
    return _NON_ALNUM_RE.sub(" ", text.lower()).strip()


def split_entry(text):
    return [part.strip() for part in _SPLIT_RE.split(text) if part.strip()]


@dataclass
class MatchResult:
    exam_id: int | None
    confidence: float
    candidates: list[dict] = field(default_factory=list)


class CatalogIndex:
    def __init__(self, exams):
        self.aliases = []
        self.alias_exam_ids = []
        self.alias_digits = []
        self.exact = {}
        for exam in exams:
            for alias in [exam.name, *exam.synonym_list]:
                key = normalize(alias)
                if not key:
                    continue
                self.aliases.append(key)
                self.alias_exam_ids.append(exam.id)
                self.alias_digits.append(set(DIGITS_RE.findall(key)))
                self.exact.setdefault(key, exam.id)

    def match(self, text, suggest_threshold=0.75):
        query = normalize(text)
        if not query or not self.aliases:
            return MatchResult(None, 0.0)
        if query in self.exact:
            exam_id = self.exact[query]
            return MatchResult(exam_id, 1.0, [{"exam_id": exam_id, "score": 1.0}])

        scorer = fuzz.ratio if len(query) <= _SHORT_QUERY else fuzz.WRatio
        query_digits = set(DIGITS_RE.findall(query))
        best = {}
        for _, score, idx in process.extract(query, self.aliases, scorer=scorer, limit=None):
            score /= 100
            # "Vitamina B12" must not become "Vitamina D", nor "T3" become "T4".
            if not query_digits <= self.alias_digits[idx]:
                score = min(score, _DIGIT_MISMATCH_CAP)
            exam_id = self.alias_exam_ids[idx]
            best[exam_id] = max(best.get(exam_id, 0.0), score)
        ranked = sorted(best.items(), key=lambda item: item[1], reverse=True)[:3]
        candidates = [{"exam_id": e, "score": round(s, 3)} for e, s in ranked if s >= suggest_threshold]
        if not candidates:
            return MatchResult(None, 0.0)
        return MatchResult(candidates[0]["exam_id"], candidates[0]["score"], candidates)
