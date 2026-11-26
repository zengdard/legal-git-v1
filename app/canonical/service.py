"""Domain services for documents, nodes and hierarchy integrity.

Hierarchy rules enforced here (acceptance criteria B):
- parent-child relationships cannot cross documents;
- cycles are rejected;
- source order is preserved via sort_order;
- cross-references (Relationship) are stored separately from the hierarchy.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.canonical.models import Document, Node
from app.core import make_document_id, make_node_id


class DomainError(Exception):
    """Domain rule violation, converted to an API error by the caller."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def get_or_create_document(
    session: Session,
    *,
    source_id: str,
    jurisdiction: str,
    slug: str,
    title: str,
    document_type: str,
    official_identifier: str | None = None,
    upstream_id: str | None = None,
    status: str | None = None,
    meta: dict | None = None,
) -> tuple[Document, bool]:
    document_id = make_document_id(jurisdiction, slug)
    document = session.get(Document, document_id)
    if document is not None:
        return document, False
    document = Document(
        id=document_id,
        jurisdiction=jurisdiction,
        document_type=document_type,
        title=title,
        official_identifier=official_identifier,
        source_id=source_id,
        upstream_id=upstream_id,
        status=status,
        meta=meta or {},
    )
    session.add(document)
    session.flush()
    return document, True


def validate_parent(session: Session, document_id: str, parent_id: str | None) -> None:
    """A node's parent must exist and belong to the same document."""
    if parent_id is None:
        return
    parent = session.get(Node, parent_id)
    if parent is None:
        raise DomainError("invalid_parent", f"parent node {parent_id!r} does not exist")
    if parent.document_id != document_id:
        raise DomainError(
            "parent_document_mismatch",
            f"parent node {parent_id!r} belongs to document {parent.document_id!r}, "
            f"cannot be the parent of a node of {document_id!r}",
        )


def check_no_cycles(session: Session, document_id: str, parent_id: str | None) -> None:
    if parent_id is None:
        return
    seen: set[str] = set()
    current_id: str | None = parent_id
    while current_id is not None:
        if current_id in seen:
            raise DomainError(
                "hierarchy_cycle", f"parent chain of node introduces a cycle at {current_id!r}"
            )
        seen.add(current_id)
        current = session.get(Node, current_id)
        if current is None or current.document_id != document_id:
            break
        current_id = current.parent_id


def get_or_create_node(
    session: Session,
    *,
    document_id: str,
    node_type: str,
    identifier: str,
    parent_id: str | None,
    label: str | None,
    sort_order: int,
    upstream_id: str | None = None,
    meta: dict | None = None,
) -> tuple[Node, bool]:
    node_id = make_node_id(document_id, node_type, identifier)
    existing = session.get(Node, node_id)
    if existing is not None:
        return existing, False

    validate_parent(session, document_id, parent_id)
    check_no_cycles(session, document_id, parent_id)

    node = Node(
        id=node_id,
        document_id=document_id,
        parent_id=parent_id,
        node_type=node_type,
        label=label,
        identifier=identifier,
        sort_order=sort_order,
        upstream_id=upstream_id,
        meta=meta or {},
    )
    session.add(node)
    session.flush()
    return node, True


def get_node(session: Session, node_id: str) -> Node | None:
    return session.get(Node, node_id)


def list_children(session: Session, node_id: str) -> list[Node]:
    statement = (
        select(Node)
        .where(Node.parent_id == node_id)
        .order_by(Node.sort_order, Node.id)
    )
    return list(session.scalars(statement))


def build_tree(session: Session, document: Document) -> dict[str, Any]:
    """Full ordered hierarchy of a document as nested dicts."""
    statement = (
        select(Node)
        .where(Node.document_id == document.id)
        .order_by(Node.sort_order, Node.id)
    )
    nodes = list(session.scalars(statement))

    children: dict[str | None, list[Node]] = {}
    for node in nodes:
        children.setdefault(node.parent_id, []).append(node)

    def serialize(node: Node, ancestors: frozenset[str]) -> dict[str, Any]:
        if node.id in ancestors:  # defensive; creation-time guards prevent this
            raise DomainError(
                "hierarchy_cycle", f"cycle detected at node {node.id!r}"
            )
        return {
            "id": node.id,
            "document_id": node.document_id,
            "parent_id": node.parent_id,
            "node_type": node.node_type,
            "label": node.label,
            "identifier": node.identifier,
            "sort_order": node.sort_order,
            "upstream_id": node.upstream_id,
            "metadata": node.meta,
            "children": [
                serialize(child, ancestors | {node.id})
                for child in children.get(node.id, [])
            ],
        }

    return {
        "document_id": document.id,
        "roots": [serialize(node, frozenset()) for node in children.get(None, [])],
    }
