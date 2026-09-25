"""Canonical graph data model for the Research Intelligence knowledge graph.

The graph renders the research evidence chain:

    SOURCE --SUPPORTS--> FINDING --ABOUT--> ENTITY
    ENTITY --RELATED_TO--> ENTITY (evidence-backed)

Every node and relationship is a plain serializable structure. The model is
database-independent: both the Neo4j adapter and the local fallback build the
exact same shapes through build_graph(), so the browser always receives a
consistent graph regardless of backend.

Nodes carry provenance (source references + confidence) and relationships carry
evidence so every graph edge can be traced back Entity -> Relationship ->
Finding -> Source.
"""

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List

# Supported graph node types (lowercase, browser-facing).
NODE_TYPES = {
    "source",
    "finding",
    "person",
    "organization",
    "location",
    "topic",
    "technology",
    "article",
    "event",
    "other",
}

# Entity-level node types that are user-facing and shown in filters.
ENTITY_NODE_TYPES = (
    "person",
    "organization",
    "location",
    "topic",
    "technology",
    "article",
    "event",
    "other",
)

# Mapping from stored entity label (extraction vocabulary) to graph node type.
ENTITY_TYPE_MAP = {
    "Person": "person",
    "Organization": "organization",
    "Location": "location",
    "Topic": "topic",
    "Technology": "technology",
    "Publication": "article",
    "Article": "article",
    "Event": "event",
    "Community": "other",
    "TimePeriod": "other",
    "Theme": "topic",
    "CulturalPractice": "other",
}

# Canonical relationship types. Every one originates from the research data.
RELATIONSHIP_TYPES = {
    "SUPPORTS",      # Source -> Finding (source underpins the finding)
    "DRAWS_ON",      # Finding -> Source (finding cites the source)
    "ABOUT",         # Finding -> Entity (finding concerns the entity)
    "MENTIONS",      # Source -> Entity (source mentions the entity)
    "CONCERNS",      # Finding/Entity -> Project scope marker
    "RELATED_TO",    # Entity -> Entity (entities co-mentioned in research)
    "BELONGS_TO",    # Entity -> Entity (membership, e.g. OpenAI -> AI org)
    "DEVELOPS",      # Entity -> Entity (organization develops technology)
    "AFFILIATED_WITH",  # Entity -> Entity (person affiliated with org)
    "AFFECTS",       # Entity -> Entity (tech affects a topic/entity)
    "INFLUENCES",    # Entity -> Entity (general influence)
    "HAS_ENTITY",    # Project -> Entity (scoping marker)
}

SOURCE_NODE = "source"
FINDING_NODE = "finding"


@dataclass
class Node:
    id: str
    name: str
    type: str
    description: str = ""
    confidence: float = 0.0
    confidence_label: str = ""
    source_references: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Relationship:
    id: str
    source_node_id: str
    target_node_id: str
    relationship_type: str
    confidence: float = 0.0
    confidence_label: str = ""
    evidence: str = ""          # human-readable citation / source reference
    source_url: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def map_entity_type(entity_type: str) -> str:
    return ENTITY_TYPE_MAP.get(entity_type, "other")


def _dedupe(values: List[str]) -> List[str]:
    seen = set()
    out = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            out.append(value)
    return out


def _normalize_entities(entities: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Filter out meaningless/junk entities (months, days, boilerplate)."""
    from .extraction import is_meaningless_entity

    cleaned = []
    seen = set()
    for entity in entities:
        name = str(entity.get("name") or entity.get("title") or "").strip()
        entity_type = map_entity_type(str(entity.get("type") or "other"))
        if not name:
            continue
        # Demo/seed entities are exempt from the meaningless filter so the
        # visibility dataset is preserved (they are intentionally curated).
        if not entity.get("demo") and is_meaningless_entity(name, entity.get("type") or "Topic"):
            continue
        key = (entity_type, name.lower())
        if key in seen:
            continue
        seen.add(key)
        entity = dict(entity, type=entity_type)
        cleaned.append(entity)
    return cleaned


def _node_id(entity: Dict[str, Any], kind: str) -> str:
    return str(entity.get("id") or f"{kind}:{entity.get('name', '').lower()}")


def build_graph(sources, findings, entities, seed_relationships=None) -> Dict[str, Any]:
    """Build a serializable {nodes, relationships} graph from research data.

    Parameters mirror the repository outputs:
      sources     -> list of source dicts (id, title, url, kind, ...)
      findings    -> list of finding dicts (id, title, text, confidence, sources, evidence)
      entities    -> list of entity dicts (id, name, type, confidence, sourceId, ...)
      seed_relationships -> optional explicit Entity->Entity links used for
                            demo/seed data (never fabricated from nothing).
    """
    nodes = []
    node_by_id = {}
    relationships = []
    seen_edges = set()

    def ensure_node(node: Node) -> None:
        existing = node_by_id.get(node.id)
        if existing is not None:
            existing.source_references = _dedupe(existing.source_references + node.source_references)
            return
        node_by_id[node.id] = node
        nodes.append(node)

    def add_edge(relationship: Relationship) -> None:
        if relationship.source_node_id not in node_by_id:
            return
        if relationship.target_node_id not in node_by_id:
            return
        edge_key = (relationship.source_node_id, relationship.relationship_type,
                    relationship.target_node_id)
        if edge_key in seen_edges:
            return
        seen_edges.add(edge_key)
        relationships.append(relationship)

    # --- Source nodes ---
    source_by_id = {}
    url_to_source_id = {}
    for source in sources:
        source_id = str(source.get("id") or source.get("url") or "")
        if not source_id:
            continue
        source_by_id[source_id] = source
        url = str(source.get("url") or "")
        if url:
            url_to_source_id[url] = source_id
        ensure_node(Node(
            id=source_id,
            name=str(source.get("title") or source.get("url") or "Untitled source"),
            type=SOURCE_NODE,
            description=str(source.get("description") or ""),
            source_references=[str(source.get("url") or "")],
            metadata={
                "kind": source.get("kind", ""),
                "url": source.get("url", ""),
                "ingestionStatus": source.get("ingestionStatus", ""),
                "confidenceLabel": source.get("confidenceLabel", "high"),
            },
        ))

    # --- Finding nodes + Source->Finding edges ---
    finding_by_id = {}
    finding_entities = {}
    for finding in findings:
        finding_id = str(finding.get("id") or "")
        if not finding_id:
            continue
        finding_by_id[finding_id] = finding
        ensure_node(Node(
            id=finding_id,
            name=str(finding.get("title") or "Untitled finding"),
            type=FINDING_NODE,
            description=str(finding.get("statement") or finding.get("text") or ""),
            confidence=_to_confidence(finding.get("confidence")),
            confidence_label=str(finding.get("confidence") or "unassessed"),
            metadata={"status": finding.get("status", ""), "createdAt": finding.get("createdAt", "")},
        ))
        finding_source_urls = [str(u) for u in (finding.get("sources") or []) if u]
        for url in finding_source_urls:
            source_id = url_to_source_id.get(url)
            if source_id is not None:
                source = source_by_id.get(source_id)
                add_edge(Relationship(
                    id=f"rel_src_find_{source_id}_{finding_id}",
                    source_node_id=source_id,
                    target_node_id=finding_id,
                    relationship_type="SUPPORTS",
                    evidence=f"Source '{source.get('title')}' supports finding '{finding.get('title')}'.",
                    source_url=url,
                ))
                add_edge(Relationship(
                    id=f"rel_find_draws_{finding_id}_{source_id}",
                    source_node_id=finding_id,
                    target_node_id=source_id,
                    relationship_type="DRAWS_ON",
                    evidence=f"Finding '{finding.get('title')}' draws on source '{source.get('title')}'.",
                    source_url=url,
                ))

    # --- Entity nodes + Finding->Entity + Source->Entity edges ---
    entity_by_id = {}
    for entity in _normalize_entities(entities):
        entity_id = _node_id(entity, "entity")
        entity_by_id[entity_id] = entity
        entity_source_id = str(entity.get("sourceId") or "")
        ensure_node(Node(
            id=entity_id,
            name=str(entity.get("name") or ""),
            type=str(entity.get("type") or "other"),
            description=str(entity.get("description") or ""),
            confidence=_to_confidence(entity.get("confidenceScore") or entity.get("confidence")),
            confidence_label=str(entity.get("confidenceLabel") or entity.get("confidence") or "low"),
            source_references=[str(entity.get("sourceUrl") or "")] if entity.get("sourceUrl") else [],
            metadata={
                "mentions": entity.get("mentions", 1),
                "sourceId": entity_source_id,
                "evidenceId": entity.get("evidenceId", ""),
                "demo": bool(entity.get("demo")),
            },
        ))

    # Source -> Entity MENTIONS edges (entity source is this source).
    for entity_id, entity in entity_by_id.items():
        src_id = str(entity.get("sourceId") or "")
        url = str(entity.get("sourceUrl") or "")
        key = src_id or url
        if not key:
            continue
        for source in sources:
            if str(source.get("id") or "") == key or str(source.get("url") or "") == key or (src_id and str(source.get("id") or "") == src_id):
                source_id = str(source.get("id") or key)
                add_edge(Relationship(
                    id=f"rel_src_mentions_{source_id}_{entity_id}",
                    source_node_id=source_id,
                    target_node_id=entity_id,
                    relationship_type="MENTIONS",
                    evidence=f"Source mentions entity '{entity.get('name')}'.",
                    source_url=url,
                ))
                break

    # Finding -> Entity ABOUT edges (via finding evidence / co-mention).
    # Build a lookup: entity -> set of findings that reference it.
    entity_findings: Dict[str, List[str]] = {}
    for finding in findings:
        finding_id = str(finding.get("id") or "")
        evidence = finding.get("evidence") or []
        entity_sources = finding.get("sources") or []
        for ev in evidence:
            ev_src = str(ev.get("sourceId") or "")
            url = str(ev.get("sourceUrl") or "")
            key = ev_src or url
            if not key:
                continue
            for source in sources:
                if str(source.get("id") or "") == key or str(source.get("url") or "") == key or (ev_src and str(source.get("id") or "") == ev_src):
                    source_id = str(source.get("id") or key)
                    for entity_id, entity in entity_by_id.items():
                        if str(entity.get("sourceId") or "") == source_id:
                            add_edge(Relationship(
                                id=f"rel_find_about_{finding_id}_{entity_id}",
                                source_node_id=finding_id,
                                target_node_id=entity_id,
                                relationship_type="ABOUT",
                                evidence=f"Finding '{finding.get('title')}' concerns entity '{entity.get('name')}'.",
                                source_url=url,
                            ))
                            entity_findings.setdefault(entity_id, [])
                            entity_findings[entity_id].append(finding_id)
                    break

    # --- Entity -> Entity edges ---
    # 1. Explicit seed relationships (only for clearly marked demo data).
    for seed in (seed_relationships or []):
        from_name = str(seed.get("fromName") or "")
        to_name = str(seed.get("toName") or "")
        rel_type = str(seed.get("relationship") or "RELATED_TO")
        if not from_name or not to_name:
            continue
        from_id = next((eid for eid, e in entity_by_id.items()
                        if e.get("name", "").lower() == from_name.lower()), None)
        to_id = next((eid for eid, e in entity_by_id.items()
                      if e.get("name", "").lower() == to_name.lower()), None)
        if not from_id or not to_id or from_id == to_id:
            continue
        evidence = str(seed.get("evidence") or
                       f"'{from_name}' is related to '{to_name}' (research relationship).")
        add_edge(Relationship(
            id=f"rel_seed_{from_id}_{rel_type}_{to_id}",
            source_node_id=from_id,
            target_node_id=to_id,
            relationship_type=rel_type,
            confidence=0.5,
            confidence_label="demo",
            evidence=evidence,
            source_url=str(seed.get("sourceUrl") or ""),
            metadata={"seed": True},
        ))

    # 2. RELATED_TO between entities co-mentioned in the same source (evidence-backed).
    source_entities: Dict[str, List[str]] = {}
    for entity_id, entity in entity_by_id.items():
        src_id = str(entity.get("sourceId") or "")
        url = str(entity.get("sourceUrl") or "")
        key = src_id or url
        if key:
            source_entities.setdefault(key, []).append(entity_id)
    for key, ids in source_entities.items():
        unique_ids = _dedupe(ids)
        for index in range(len(unique_ids) - 1):
            left, right = unique_ids[index], unique_ids[index + 1]
            if left == right:
                continue
            left_name = node_by_id[left].name
            right_name = node_by_id[right].name
            add_edge(Relationship(
                id=f"rel_co_{left}_{right}",
                source_node_id=left,
                target_node_id=right,
                relationship_type="RELATED_TO",
                confidence=max(node_by_id[left].confidence, node_by_id[right].confidence),
                confidence_label="co-mention",
                evidence=f"'{left_name}' and '{right_name}' co-occur within a research source.",
                source_url="",
            ))

    return {
        "nodes": [node.to_dict() for node in nodes],
        "relationships": [rel.to_dict() for rel in relationships],
    }


def _to_confidence(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if number < 0:
        return 0.0
    if number > 1:
        return 1.0
    return round(number, 2)
