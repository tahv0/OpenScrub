"""Literal matching of one already-associated text region.

This module discovers no text or geometry and has no application side effects.
An observation remains caller-owned, including all nested evidence; retaining it
here provides no lifetime or thread-safety guarantee.
"""
from dataclasses import dataclass, field
import re
from typing import List, Literal, Mapping, Optional, Tuple, Union

MatchMode = Literal["full", "fragment"]
_SEPARATORS = " \t.-"
_ALPHABET = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789" + _SEPARATORS)
_DELETE_SEPARATORS = str.maketrans("", "", _SEPARATORS)


def _normalize_query_text(value: object) -> str:
    if not isinstance(value, str) or len(value) > 128:
        raise ValueError("Each query must be a string of at most 128 characters")
    if any(character not in _ALPHABET for character in value):
        raise ValueError("Queries support ASCII letters, digits, space, tab, dot and hyphen only")
    normalized = value.translate(_DELETE_SEPARATORS).upper()
    if not 3 <= len(normalized) <= 16:
        raise ValueError("Each query must contain 3 to 16 normalized literal characters")
    return normalized


@dataclass(frozen=True)
class PlateQuery:
    """A validated, normalized literal with an explicit matching mode."""

    text: str = field(repr=False)
    mode: MatchMode = "full"

    def __post_init__(self) -> None:
        if self.mode not in ("full", "fragment"):
            raise ValueError("Query mode must be full or fragment")
        object.__setattr__(self, "text", _normalize_query_text(self.text))


@dataclass(frozen=True)
class TextMatch:
    """Evidence of literal equality or an explicitly requested fragment."""

    query: PlateQuery
    observed_text: str = field(repr=False)
    normalized_observed: str = field(repr=False)
    match_kind: Literal["full_equal", "fragment"]


@dataclass(frozen=True)
class ObservationMatch:
    """A text match retaining the complete original mapping by identity."""

    observation: Mapping[str, object] = field(repr=False)
    text_match: TextMatch


def _validated_queries(value: object) -> Tuple[PlateQuery, ...]:
    if not isinstance(value, (list, tuple)) or not 1 <= len(value) <= 10:
        raise ValueError("Prepared queries must be a list or tuple of 1 to 10 queries")
    unique = []
    seen = set()
    for query in value:
        if not isinstance(query, PlateQuery):
            raise ValueError("Prepared query entries must be PlateQuery instances")
        if query.mode not in ("full", "fragment"):
            raise ValueError("Query mode must be full or fragment")
        if _normalize_query_text(query.text) != query.text:
            raise ValueError("Prepared query text must already be normalized")
        key = (query.mode, query.text)
        if key not in seen:
            seen.add(key)
            unique.append(query)
    return tuple(unique)


def normalize_queries(
    value: Union[str, List[str], Tuple[str, ...]], *, mode: MatchMode = "full"
) -> Tuple[PlateQuery, ...]:
    """Prepare one uniform-mode batch, validating before stable deduplication."""
    if mode not in ("full", "fragment"):
        raise ValueError("Query mode must be full or fragment")
    if isinstance(value, str):
        if len(value) > 1024:
            raise ValueError("A query batch must contain at most 1024 raw characters")
        entries = [entry for entry in re.split(r"[,;\r\n]+", value) if entry.strip(" \t")]
    elif isinstance(value, (list, tuple)):
        if any(not isinstance(entry, str) for entry in value):
            raise ValueError("Query batch entries must be strings")
        if sum(len(entry) for entry in value) > 1024:
            raise ValueError("A query batch must contain at most 1024 raw characters")
        entries = value
    else:
        raise ValueError("Queries must be a string or a list or tuple of strings")
    if not 1 <= len(entries) <= 10:
        raise ValueError("A query batch must contain 1 to 10 nonempty queries before deduplication")
    return _validated_queries(tuple(PlateQuery(entry, mode) for entry in entries))


def _normalize_observed_text(value: object) -> Optional[str]:
    if not isinstance(value, str) or len(value) > 512:
        return None
    if any(character not in _ALPHABET for character in value):
        return None
    normalized = value.translate(_DELETE_SEPARATORS).upper()
    return normalized if len(normalized) >= 3 else None


def match_text(
    observed: object, queries: Union[List[PlateQuery], Tuple[PlateQuery, ...]]
) -> Tuple[TextMatch, ...]:
    """Match one supplied region, returning all unique queries in query order."""
    prepared = _validated_queries(queries)
    normalized = _normalize_observed_text(observed)
    if normalized is None:
        return ()
    matches = []
    for query in prepared:
        if query.mode == "full" and normalized == query.text:
            matches.append(TextMatch(query, observed, normalized, "full_equal"))
        elif query.mode == "fragment" and query.text in normalized:
            matches.append(TextMatch(query, observed, normalized, "fragment"))
    return tuple(matches)


def match_observation(
    observation: object, queries: Union[List[PlateQuery], Tuple[PlateQuery, ...]]
) -> Tuple[ObservationMatch, ...]:
    """Wrap matches without copying, narrowing or interpreting other evidence."""
    prepared = _validated_queries(queries)
    if not isinstance(observation, Mapping):
        return ()
    return tuple(ObservationMatch(observation, match)
                 for match in match_text(observation.get("text"), prepared))
