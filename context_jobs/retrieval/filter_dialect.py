"""
Canonical metadata-filter dialect (Pinecone-shaped) and provider translators.

Internal dialect operators used across Context Jobs:
  {"field": {"$eq": value}}
  {"field": {"$in": [..]}}
  {"$and": [clause, ...]}
  {"$or": [clause, ...]}

Adapters receive this dialect and translate at the boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


_SUPPORTED_OPS = frozenset({"$eq", "$in"})
_LOGICAL = frozenset({"$and", "$or"})


@dataclass(frozen=True)
class FilterLeaf:
    field: str
    op: str  # $eq | $in
    value: Any


@dataclass(frozen=True)
class FilterNode:
    """Logical tree: either a leaf or an and/or of children."""

    kind: str  # leaf | and | or
    leaf: FilterLeaf | None = None
    children: tuple["FilterNode", ...] = ()


def parse_metadata_filter(filter_dict: dict[str, Any] | None) -> FilterNode | None:
    """Parse a Pinecone-shaped filter into a provider-neutral tree."""
    if not filter_dict or not isinstance(filter_dict, dict):
        return None
    return _parse_node(filter_dict)


def _parse_node(node: dict[str, Any]) -> FilterNode:
    if not isinstance(node, dict) or not node:
        raise ValueError("Metadata filter node must be a non-empty object.")

    keys = list(node.keys())
    if len(keys) == 1 and keys[0] in _LOGICAL:
        op = keys[0]
        raw_children = node[op]
        if not isinstance(raw_children, list) or not raw_children:
            raise ValueError(f"{op} requires a non-empty list.")
        children = tuple(_parse_node(child) for child in raw_children if isinstance(child, dict))
        if not children:
            raise ValueError(f"{op} produced no valid child clauses.")
        return FilterNode(kind="and" if op == "$and" else "or", children=children)

    # Single-field clause or implicit $and of field clauses
    leaves: list[FilterNode] = []
    for field, spec in node.items():
        if field in _LOGICAL:
            raise ValueError("Logical operators must be the sole key in a filter node.")
        if not isinstance(field, str) or not field.strip():
            raise ValueError("Metadata filter field names must be non-empty strings.")
        if not isinstance(spec, dict) or len(spec) != 1:
            raise ValueError(
                f"Field {field!r} must map to a single operator object, e.g. {{'$eq': value}}."
            )
        op, value = next(iter(spec.items()))
        if op not in _SUPPORTED_OPS:
            raise ValueError(f"Unsupported metadata filter operator {op!r} on field {field!r}.")
        if op == "$in":
            if not isinstance(value, list) or not value:
                raise ValueError(f"$in on {field!r} requires a non-empty list.")
        leaves.append(
            FilterNode(
                kind="leaf",
                leaf=FilterLeaf(field=field.strip(), op=op, value=value),
            )
        )

    if len(leaves) == 1:
        return leaves[0]
    return FilterNode(kind="and", children=tuple(leaves))


def to_qdrant_filter(filter_dict: dict[str, Any] | None) -> Any | None:
    """Translate dialect → qdrant_client.models.Filter."""
    tree = parse_metadata_filter(filter_dict)
    if tree is None:
        return None

    from qdrant_client.models import FieldCondition, Filter, MatchAny, MatchValue

    def _leaf(leaf: FilterLeaf) -> FieldCondition:
        if leaf.op == "$eq":
            return FieldCondition(key=leaf.field, match=MatchValue(value=leaf.value))
        return FieldCondition(
            key=leaf.field,
            match=MatchAny(any=[v for v in leaf.value]),
        )

    def _build(node: FilterNode) -> Filter | FieldCondition:
        if node.kind == "leaf":
            assert node.leaf is not None
            return _leaf(node.leaf)
        parts = [_build(child) for child in node.children]
        normalized: list[Any] = []
        for part in parts:
            if isinstance(part, Filter):
                if node.kind == "and" and part.must and not part.should and not part.must_not:
                    normalized.extend(list(part.must))
                elif node.kind == "or" and part.should and not part.must and not part.must_not:
                    normalized.extend(list(part.should))
                else:
                    normalized.append(part)
            else:
                normalized.append(part)
        if node.kind == "and":
            return Filter(must=normalized)
        # OR: at least one should-clause must match.
        return Filter(should=normalized)

    built = _build(tree)
    if isinstance(built, Filter):
        return built
    return Filter(must=[built])


def to_weaviate_filter(filter_dict: dict[str, Any] | None) -> Any | None:
    """Translate dialect → weaviate.classes.query.Filter expression."""
    tree = parse_metadata_filter(filter_dict)
    if tree is None:
        return None

    from weaviate.classes.query import Filter

    def _leaf(leaf: FilterLeaf) -> Any:
        prop = Filter.by_property(leaf.field)
        if leaf.op == "$eq":
            return prop.equal(leaf.value)
        # $in → OR of equals
        parts = [Filter.by_property(leaf.field).equal(v) for v in leaf.value]
        expr = parts[0]
        for part in parts[1:]:
            expr = expr | part
        return expr

    def _build(node: FilterNode) -> Any:
        if node.kind == "leaf":
            assert node.leaf is not None
            return _leaf(node.leaf)
        parts = [_build(child) for child in node.children]
        expr = parts[0]
        for part in parts[1:]:
            expr = (expr & part) if node.kind == "and" else (expr | part)
        return expr

    return _build(tree)


def to_pgvector_predicate(
    filter_dict: dict[str, Any] | None,
    *,
    metadata_column: str,
) -> tuple[str, list[Any]] | None:
    """
    Translate dialect → SQL boolean expression + bound params.

    Uses JSONB text extraction: metadata_column ->> 'field'
    Identifier must already be validated by the adapter.
    """
    tree = parse_metadata_filter(filter_dict)
    if tree is None:
        return None

    params: list[Any] = []

    def _quote_ident(name: str) -> str:
        # Adapter validates identifiers; still quote for safety.
        return '"' + name.replace('"', '""') + '"'

    col = _quote_ident(metadata_column)

    def _leaf(leaf: FilterLeaf) -> str:
        field_lit = leaf.field.replace("'", "''")
        extractor = f"({col} ->> '{field_lit}')"
        if leaf.op == "$eq":
            params.append(str(leaf.value))
            return f"{extractor} = %s"
        placeholders = []
        for item in leaf.value:
            params.append(str(item))
            placeholders.append("%s")
        return f"{extractor} IN ({', '.join(placeholders)})"

    def _build(node: FilterNode) -> str:
        if node.kind == "leaf":
            assert node.leaf is not None
            return _leaf(node.leaf)
        joiner = " AND " if node.kind == "and" else " OR "
        return "(" + joiner.join(_build(child) for child in node.children) + ")"

    return _build(tree), params


def collect_filter_fields(filter_dict: dict[str, Any] | None) -> set[str]:
    """Return all leaf field names referenced by a filter (for schema prep)."""
    tree = parse_metadata_filter(filter_dict)
    if tree is None:
        return set()

    fields: set[str] = set()

    def _walk(node: FilterNode) -> None:
        if node.kind == "leaf" and node.leaf is not None:
            fields.add(node.leaf.field)
            return
        for child in node.children:
            _walk(child)

    _walk(tree)
    return fields
