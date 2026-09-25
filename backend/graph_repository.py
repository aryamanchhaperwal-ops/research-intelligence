"""Graph repository abstraction for the knowledge graph.

Adapters read the research data (sources, findings, entities) from either the
Neo4j-backed repository or the local in-memory store and build an identical
graph shape through graph_model.build_graph(). This keeps a single, clean graph
contract regardless of whether a graph database is available.
"""

from typing import Any, Dict, List, Protocol, runtime_checkable

from .graph_model import build_graph


@runtime_checkable
class GraphRepository(Protocol):
    storage_name: str

    def graph(self, project_slug: str) -> Dict[str, Any]: ...

    def nodes(self, project_slug: str) -> List[Dict[str, Any]]: ...

    def relationships(self, project_slug: str) -> List[Dict[str, Any]]: ...

    def search(self, project_slug: str, term: str) -> List[Dict[str, Any]]: ...

    def node(self, project_slug: str, node_id: str) -> Dict[str, Any]: ...


class _BaseGraphRepository:
    storage_name = "graph"

    def _raw_data(self, project_slug: str):
        raise NotImplementedError

    def graph(self, project_slug: str) -> Dict[str, Any]:
        sources, findings, entities, seeds = self._raw_data(project_slug)
        return build_graph(sources, findings, entities, seed_relationships=seeds)

    def nodes(self, project_slug: str) -> List[Dict[str, Any]]:
        return self.graph(project_slug)["nodes"]

    def relationships(self, project_slug: str) -> List[Dict[str, Any]]:
        graph = self.graph(project_slug)
        by_id = {n["id"]: n for n in graph["nodes"]}
        rows = []
        for rel in graph["relationships"]:
            source = by_id.get(rel["source_node_id"], {})
            target = by_id.get(rel["target_node_id"], {})
            rows.append({
                **rel,
                "sourceName": source.get("name", ""),
                "sourceType": source.get("type", ""),
                "targetName": target.get("name", ""),
                "targetType": target.get("type", ""),
            })
        return rows

    def search(self, project_slug: str, term: str) -> List[Dict[str, Any]]:
        term = (term or "").strip().lower()
        if not term:
            return []
        graph = self.graph(project_slug)
        return [
            node for node in graph["nodes"]
            if term in str(node.get("name") or "").lower()
            or term in str(node.get("description") or "").lower()
        ]

    def node(self, project_slug: str, node_id: str) -> Dict[str, Any]:
        graph = self.graph(project_slug)
        node = next((n for n in graph["nodes"] if n["id"] == node_id), None)
        if node is None:
            raise KeyError("Node not found in graph.")
        by_id = {n["id"]: n for n in graph["nodes"]}
        relationships = [
            {
                "id": rel["id"],
                "relationshipType": rel["relationship_type"],
                "confidence": rel["confidence"],
                "confidenceLabel": rel["confidence_label"],
                "evidence": rel["evidence"],
                "sourceUrl": rel["source_url"],
                "direction": "source" if rel["source_node_id"] == node_id else "target",
                "otherNodeId": rel["target_node_id"] if rel["source_node_id"] == node_id else rel["source_node_id"],
                "otherNodeName": by_id[rel["target_node_id"] if rel["source_node_id"] == node_id else rel["source_node_id"]].get("name"),
                "otherNodeType": by_id[rel["target_node_id"] if rel["source_node_id"] == node_id else rel["source_node_id"]].get("type"),
                "seed": rel.get("metadata", {}).get("seed", False),
            }
            for rel in graph["relationships"]
            if rel["source_node_id"] == node_id or rel["target_node_id"] == node_id
        ]
        node_relationships = graph["relationships"]
        related_findings = _related_of_type(node_relationships, node_id, "ABOUT")
        related_sources = _related_of_type(node_relationships, node_id, "SUPPORTS") + \
            _related_of_type(node_relationships, node_id, "MENTIONS")
        source_references = [
            {"type": "source", "id": ref_id, "name": by_id[ref_id].get("name")}
            for ref_id in _referenced_sources(node_relationships, node_id)
            if ref_id in by_id
        ]
        return {
            **node,
            "relationships": relationships,
            "connected": [
                {"id": rel["otherNodeId"], "name": rel["otherNodeName"],
                 "type": rel["otherNodeType"], "relationshipType": rel["relationshipType"]}
                for rel in relationships
            ],
            "relatedFindings": [
                {"id": fid, "name": by_id[fid].get("name")}
                for fid in _related_of_type(node_relationships, node_id, "ABOUT")
                if fid in by_id
            ],
            "relatedSources": [
                {"id": sid, "name": by_id[sid].get("name")}
                for sid in related_sources
                if sid in by_id
            ],
            "evidence": [
                {
                    "id": other_id,
                    "name": by_id[other_id].get("name"),
                    "evidence": rel.get("evidence", ""),
                    "sourceUrl": rel.get("source_url", ""),
                }
                for rel in node_relationships
                if (rel["source_node_id"] == node_id or rel["target_node_id"] == node_id)
                for other_id in (
                    [rel["target_node_id"] if rel["source_node_id"] == node_id
                     else rel["source_node_id"]]
                )
                if other_id in by_id and by_id[other_id]["type"] == FINDING
            ],
        }


FINDING = "finding"


def _related_of_type(relationships, node_id, rel_type):
    out = []
    for rel in relationships:
        if rel["relationship_type"] != rel_type:
            continue
        if rel["source_node_id"] == node_id:
            out.append(rel["target_node_id"])
        elif rel["target_node_id"] == node_id:
            out.append(rel["source_node_id"])
    return out


def _referenced_sources(relationships, node_id):
    out = []
    for rel in relationships:
        if rel["source_node_id"] == node_id or rel["target_node_id"] == node_id:
            other = rel["target_node_id"] if rel["source_node_id"] == node_id else rel["source_node_id"]
            out.append(other)
    return out


class LocalGraphRepository(_BaseGraphRepository):
    storage_name = "local"

    def __init__(self, store=None):
        self._store = store

    def _raw_data(self, project_slug):
        store = self._store
        sources = store.sources(project_slug) if hasattr(store, "sources") else []
        findings = store.findings(project_slug) if hasattr(store, "findings") else []
        entities = store.entities(project_slug) if hasattr(store, "entities") else []
        seeds = store.seed_relationships(project_slug) if hasattr(store, "seed_relationships") else []
        return sources, findings, entities, seeds


class Neo4jGraphRepository(_BaseGraphRepository):
    storage_name = "neo4j"

    def __init__(self, repository=None):
        self._repository = repository

    def _raw_data(self, project_slug):
        repository = self._repository
        sources = repository.sources(project_slug) if hasattr(repository, "sources") else []
        findings = repository.findings(project_slug) if hasattr(repository, "findings") else []
        entities = repository.entities(project_slug) if hasattr(repository, "entities") else []
        seeds = repository.seed_relationships(project_slug) if hasattr(repository, "seed_relationships") else []
        return sources, findings, entities, seeds
