import unittest

from backend.graph_model import build_graph, map_entity_type, NODE_TYPES
from backend.graph_repository import LocalGraphRepository
from backend.memory_store import MemoryStore


class GraphModelTests(unittest.TestCase):
    def test_map_entity_type_normalizes_labels(self):
        self.assertEqual(map_entity_type("Organization"), "organization")
        self.assertEqual(map_entity_type("Publication"), "article")
        self.assertEqual(map_entity_type("Unknown"), "other")

    def test_node_types_are_stable(self):
        for expected in ("source", "finding", "person", "organization",
                         "location", "topic", "technology", "article",
                         "event", "other"):
            self.assertIn(expected, NODE_TYPES)

    def test_build_graph_connects_source_finding_entity(self):
        graph = build_graph(
            sources=[{"id": "s1", "title": "Report", "url": "https://x"}],
            findings=[{"id": "f1", "title": "Finding",
                       "sources": ["https://x"],
                       "evidence": [{"sourceUrl": "https://x"}]}],
            entities=[
                {"id": "e1", "name": "OpenAI", "type": "Organization",
                 "sourceId": "s1", "sourceUrl": "https://x"},
            ],
        )
        names = {n["name"]: n["type"] for n in graph["nodes"]}
        self.assertEqual(names["Report"], "source")
        self.assertEqual(names["Finding"], "finding")
        self.assertEqual(names["OpenAI"], "organization")
        types = {r["relationship_type"] for r in graph["relationships"]}
        self.assertIn("SUPPORTS", types)   # Source -> Finding
        self.assertIn("ABOUT", types)      # Finding -> Entity
        self.assertIn("MENTIONS", types)   # Source -> Entity

    def test_build_graph_drops_meaningless_entities(self):
        graph = build_graph([], [], [
            {"id": "m1", "name": "April", "type": "Topic",
             "sourceId": "s", "sourceUrl": "u"},
            {"id": "e1", "name": "OpenAI", "type": "Organization",
             "sourceId": "s", "sourceUrl": "u"},
        ])
        names = {n["name"] for n in graph["nodes"]}
        self.assertEqual(names, {"OpenAI"})

    def test_seed_relationships_are_honoured(self):
        graph = build_graph([], [], [
            {"id": "a", "name": "OpenAI", "type": "Organization",
             "sourceId": "s", "sourceUrl": "u", "demo": True},
            {"id": "b", "name": "GPT", "type": "Technology",
             "sourceId": "s", "sourceUrl": "u", "demo": True},
        ], seed_relationships=[
            {"fromName": "OpenAI", "toName": "GPT", "relationship": "DEVELOPS"},
        ])
        devs = [r for r in graph["relationships"]
                if r["relationship_type"] == "DEVELOPS"]
        self.assertEqual(len(devs), 1)


class LocalGraphRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.store = MemoryStore(seed=True)
        self.repo = LocalGraphRepository(self.store)

    def test_graph_data_is_consistent(self):
        graph = self.repo.graph("public-ai-research-source-validation-2026-08-28")
        self.assertTrue(graph["nodes"])
        self.assertTrue(graph["relationships"])
        self.assertEqual(len(self.repo.nodes(
            "public-ai-research-source-validation-2026-08-28")), len(graph["nodes"]))
        self.assertEqual(len(self.repo.relationships(
            "public-ai-research-source-validation-2026-08-28")), len(graph["relationships"]))

    def test_node_detail_returns_evidence_chain(self):
        node = self.repo.node("public-ai-research-source-validation-2026-08-28",
                              self._id("OpenAI"))
        self.assertEqual(node["type"], "organization")
        self.assertTrue(node["relationships"])
        self.assertTrue(node["evidence"] or node["relatedFindings"])

    def test_search_is_scoped_and_matches(self):
        results = self.repo.search(
            "public-ai-research-source-validation-2026-08-28", "gpt")
        self.assertTrue(results)

    def _id(self, name):
        graph = self.repo.graph("public-ai-research-source-validation-2026-08-28")
        return next(n["id"] for n in graph["nodes"] if n["name"] == name)


if __name__ == "__main__":
    unittest.main()
