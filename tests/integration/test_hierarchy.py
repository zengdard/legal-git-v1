"""Acceptance criteria B: canonical hierarchy."""

from __future__ import annotations

import pytest
from sqlalchemy import select, text

from app.canonical import service as canonical
from app.canonical.models import Document, Node, Relationship
from app.canonical.service import DomainError
from tests.conftest import DOC_ID, NODE_1103, NODE_1104

NODE_1105 = "lg:fr:code-civil:article:1105"


def test_tree_structure_and_order(session, source, store, corpus):
    document = session.get(Document, DOC_ID)
    tree = canonical.build_tree(session, document)
    (root,) = tree["roots"]
    assert root["node_type"] == "livre"
    assert root["id"] == "lg:fr:code-civil:livre:iii"
    (titre,) = root["children"]
    assert titre["id"] == "lg:fr:code-civil:titre:iii"
    # Source order among siblings is preserved (release 2 order); article
    # 9999 (present only in release 1) keeps its logical identity and its
    # original position from release 1.
    children_ids = [c["id"] for c in titre["children"]]
    assert children_ids == [
        "lg:fr:code-civil:article:1101",
        NODE_1103,
        NODE_1104,
        "lg:fr:code-civil:article:1105",
        "lg:fr:code-civil:article:9999",
    ]
    # sort_order keeps the first-seen source position (release 1 positions
    # are never silently mutated); nodes added later get their release-2
    # position. Divergence is visible via the changes endpoint.
    assert [c["sort_order"] for c in titre["children"]] == [0, 0, 1, 2, 3]


def test_node_points_to_document_and_parent(session, corpus):
    node = session.get(Node, NODE_1103)
    assert node.document_id == DOC_ID
    assert node.parent_id == "lg:fr:code-civil:titre:iii"


def test_cross_document_parent_rejected(session, source, store, corpus):
    other_doc = Document(
        id="lg:fr:code-penal",
        jurisdiction="fr",
        document_type="code",
        title="Code pénal (test)",
        source_id=source.id,
    )
    session.add(other_doc)
    session.flush()
    titre = session.get(Node, "lg:fr:code-civil:titre:iii")
    with pytest.raises(DomainError) as exc_info:
        canonical.get_or_create_node(
            session,
            document_id=other_doc.id,
            node_type="article",
            identifier="1-1",
            parent_id=titre.id,  # parent belongs to the other document
            label="Article 1-1",
            sort_order=0,
        )
    assert exc_info.value.code == "parent_document_mismatch"


def test_cycle_rejected(session, source, store, corpus):
    """Creation-time guards make cycles impossible through the service.

    With single-parent adjacency, a corrupted cycle (injected here by raw
    SQL) forms its own detached component; the meaningful defence is that
    nothing new can be attached to the corrupted chain: check_no_cycles
    rejects it while walking the ancestors.
    """
    session.execute(
        text("UPDATE nodes SET parent_id = :a WHERE id = :b"),
        {"a": NODE_1105, "b": NODE_1104},
    )
    session.execute(
        text("UPDATE nodes SET parent_id = :b WHERE id = :a"),
        {"a": NODE_1105, "b": NODE_1104},
    )
    session.flush()

    with pytest.raises(DomainError) as exc_info:
        canonical.get_or_create_node(
            session,
            document_id=DOC_ID,
            node_type="alinea",
            identifier="1-4-1",
            parent_id=NODE_1104,  # ancestor chain walks 1104 -> 1105 -> 1104
            label="Alinéa 1",
            sort_order=0,
        )
    assert exc_info.value.code == "hierarchy_cycle"
    session.rollback()


def test_relationships_are_separate_from_hierarchy(session, corpus):
    relationships = list(session.scalars(select(Relationship)))
    assert len(relationships) == 1
    relationship = relationships[0]
    assert relationship.from_node_id == NODE_1103
    assert relationship.relationship_type == "related_to"
    assert relationship.meta["upstream_type"] == "CONTEXTE"
    # Not a child of the article:
    node_1103 = session.get(Node, NODE_1103)
    children = canonical.list_children(session, node_1103.id)
    assert children == []
