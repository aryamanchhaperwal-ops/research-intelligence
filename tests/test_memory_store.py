import unittest
import uuid

from backend.memory_store import MemoryStore


class MemoryStoreTests(unittest.TestCase):
    def setUp(self):
        self.store = MemoryStore(seed=True)

    def test_seed_provides_clearly_labeled_demo_projects(self):
        projects = self.store.list_projects()
        self.assertGreaterEqual(len(projects), 3)
        fixture = [p for p in projects if p["name"].endswith("(DEMO)")]
        self.assertGreaterEqual(len(fixture), 2)
        # The Public AI demo project is seeded with clearly-marked sample data.
        slugs = {p["slug"] for p in projects}
        self.assertIn("public-ai-research-source-validation-2026-08-28", slugs)

    def test_public_ai_project_exposes_seed_graph(self):
        graph = self.store.graph_data(
            "public-ai-research-source-validation-2026-08-28")
        names = {node["name"] for node in graph["nodes"]}
        self.assertIn("OpenAI", names)
        self.assertIn("GPT", names)
        relationship_types = {rel["relationship_type"] for rel in graph["relationships"]}
        self.assertTrue(relationship_types & {"DEVELOPS", "BELONGS_TO"})

    def test_create_and_retrieve_project(self):
        result = self.store.create_project({
            "name": "Test Research", "domain": "technology",
            "researchQuestion": "Question?", "clientName": "Acme",
        })
        project = self.store.get_project(result["slug"])
        self.assertEqual(project["clientName"], "Acme")
        self.assertEqual(project["researchQuestion"], "Question?")

    def test_update_project(self):
        self.store.create_project({
            "name": "Before", "domain": "culture", "researchQuestion": "Q",
        })
        project = self.store.update_project("before", {
            "name": "After", "domain": "society", "researchQuestion": "Q2",
        })
        self.assertEqual(project["name"], "After")
        self.assertEqual(project["domain"], "society")

    def test_add_source_and_findings_roundtrip(self):
        result = self.store.add_source("partition-era-culture-migration-demo", {
            "title": "A real-looking source", "url": "https://example.com/x",
            "content": "OpenAI developed GPT-4 and announced new models in 2023.",
            "ingest": True,
        })
        self.assertTrue(result["documentId"])
        self.assertGreaterEqual(result["entities"], 1)
        finding_id = self.store.add_finding("partition-era-culture-migration-demo", {
            "title": "A finding", "text": "The source supports a change.",
            "source": "https://example.com/x", "confidence": "medium",
        })
        finding = self.store.get_finding(finding_id)
        self.assertEqual(finding["status"], "draft")
        self.assertGreaterEqual(len(finding["evidence"]), 1)

    def test_finding_transitions(self):
        finding_id = self.store.add_finding("partition-era-culture-migration-demo", {
            "title": "T", "text": "Text",
        })
        with self.assertRaises(ValueError):
            self.store.update_finding(finding_id, {"status": "verified"})
        updated = self.store.update_finding(finding_id, {"status": "needs_review"})
        self.assertEqual(updated["status"], "needs_review")

    def test_dashboard_metrics_and_recent_items(self):
        dashboard = self.store.dashboard()
        self.assertGreaterEqual(dashboard["metrics"]["projects"], 2)
        self.assertGreater(dashboard["metrics"]["entities"], 0)
        self.assertTrue(dashboard["recentProjects"])
        self.assertTrue(dashboard["recentFindings"])

    def test_graph_and_relationships(self):
        rows = self.store.graph("partition-era-culture-migration-demo")
        self.assertTrue(rows)
        self.assertTrue(all(row["relationship"] for row in rows))

    def test_generate_findings_is_source_driven(self):
        result = self.store.generate_findings("community-cultural-practices-survey-demo")
        self.assertGreaterEqual(result["count"], 1)
        self.assertEqual(result["generated"][0]["status"], "needs_review")

    def test_search_is_project_scoped(self):
        result = self.store.search("partition-era-culture-migration-demo", "demo")
        self.assertGreaterEqual(len(result["sources"]), 1)
        other = self.store.search("community-cultural-practices-survey-demo", "partition-culture")
        self.assertEqual(len(other["sources"]), 0)

    def test_source_ingestion_records_metadata_evidence_and_status(self):
        result = self.store.add_source("partition-era-culture-migration-demo", {
            "title": "Census coverage", "url": "https://example.com/census",
            "kind": "dataset", "author": "Stats Office", "publisher": "Archive",
            "publicationDate": "1947-08-15",
            "content": (
                "The registry reported in 1947 that 1.2 million families in "
                "Punjab relocated. The survey office in New Delhi published totals."
            ),
            "ingest": True,
        })
        self.assertEqual(result["status"], "ready")
        self.assertGreaterEqual(result["evidence"], 1)
        detail = self.store.get_source("partition-era-culture-migration-demo", result["id"])
        self.assertEqual(detail["author"], "Stats Office")
        self.assertEqual(detail["kind"], "dataset")
        self.assertEqual(detail["ingestionStatus"], "ready")
        self.assertGreaterEqual(len(detail["evidence"]), 1)
        self.assertGreaterEqual(len(detail["entities"]), 1)

    def test_metadata_only_source_registers_pending(self):
        result = self.store.add_source("partition-era-culture-migration-demo", {
            "title": "Reference", "url": "https://example.com/reference",
            "kind": "government",
        })
        self.assertEqual(result["status"], "pending")
        self.assertIsNone(result["documentId"])

    def test_sources_list_filters_by_kind_and_status(self):
        self.store.add_source("partition-era-culture-migration-demo", {
            "title": "Pending reference", "url": "https://example.com/pending-source",
            "kind": "report",
        })
        pending = self.store.sources(
            "partition-era-culture-migration-demo", status="pending")
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["ingestionStatus"], "pending")
        reports = self.store.sources(
            "partition-era-culture-migration-demo", kind="report")
        self.assertEqual(len(reports), 1)
        self.assertEqual(reports[0]["kind"], "report")

    def test_reingest_source_keeps_workflow_alive_in_demo_mode(self):
        source_id = str(uuid.uuid5(uuid.NAMESPACE_URL, "https://example.com/sample-source-partition-culture"))
        result = self.store.reingest_source("partition-era-culture-migration-demo", source_id)
        self.assertEqual(result["status"], "ready")
        self.assertGreaterEqual(result["entities"], 1)
        reingested = self.store.get_source(
            "partition-era-culture-migration-demo", source_id)
        self.assertEqual(reingested["id"], source_id)


if __name__ == "__main__":
    unittest.main()