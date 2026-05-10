"""Common types shared by all extractors."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass
class Entity:
    """A single piece of structured info extracted from text.

    `source` says which extractor produced it ("spacy", "transformer", "regex"),
    so Phase 4 can prefer one source over another when they disagree.
    """

    type: str           # PERSON, ORG, DATE, EMAIL, PHONE, URL, MONEY, ID, CODE, ...
    value: str          # the raw matched text
    confidence: float = 1.0
    source: str = ""    # extractor that produced it
    start: int = -1     # char offset in the source text (where applicable)
    end: int = -1
    normalized_value: str = ""  # canonical form (E.164 phone, ISO date, JSON for money)


@dataclass
class ExtractionResult:
    entities: List[Entity] = field(default_factory=list)

    def of_type(self, *types: str) -> List[Entity]:
        wanted = {t.upper() for t in types}
        return [e for e in self.entities if e.type.upper() in wanted]

    def best_of_type(self, *types: str) -> Entity | None:
        items = self.of_type(*types)
        if not items:
            return None
        return max(items, key=lambda e: e.confidence)
