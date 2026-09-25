import unittest
import base64
import io
from types import SimpleNamespace
from unittest.mock import patch

from backend.repository import (
    ResearchRepository,
    clean_content,
    extract_entities,
    extract_evidence,
    slugify,
)
from backend.config import http_uri


class FakeResponse:
    def __init__(self, body):
        self.body = body.encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self, size):
        return self.body[:size]


class FakeClient:
    def __init__(self):
        self.statements = []
        self.settings = SimpleNamespace(neo4j_timeout_sec=15)

    def query(self, statement, parameters=None):
        self.statements.append((statement, parameters))
        if "count(DISTINCT n) AS entities" in statement:
            return [
                {"id": "s1", "title": "Report A", "url": "https://example.com/a",
                 "kind": "report", "author": "A. Author", "publisher": "Pub",
                 "publicationDate": "1947-08-15", "description": "Notes",
                 "ingestionStatus": "ready", "ingestionError": "",
                 "createdAt": "2026-01-01", "updatedAt": "2026-01-02",
                 "entities": 2, "evidence": 3},
                {"id": "s2", "title": "Report B", "url": "https://example.com/b",
                 "kind": "article", "author": "", "publisher": "",
                 "publicationDate": "", "description": "",
                 "ingestionStatus": "failed", "ingestionError": "fetch error",
                 "createdAt": "2026-01-01", "updatedAt": "2026-01-03",
                 "entities": 0, "evidence": 0},
            ]
        if "collect(DISTINCT {id:e.id, claim" in statement:
            return [{
                "id": "s1", "title": "Report A", "url": "https://example.com/a",
                "kind": "report", "author": "A. Author", "publisher": "Pub",
                "publicationDate": "1947-08-15", "description": "Notes",
                "ingestionStatus": "ready", "ingestionError": "",
                "retrievedAt": "2026-01-02", "createdAt": "2026-01-01",
                "updatedAt": "2026-01-02", "content": "Body text.",
                "evidence": [{"id": "e1", "claim": "Claim text", "snippet": "Excerpt text",
                              "confidence": "high", "location": "sentence:1",
                              "status": "extracted", "createdAt": "2026-01-02"}],
                "entities": [{"id": "n1", "type": "Organization",
                              "name": "Acme Corporation"}],
            }]
        if "coalesce(s.kind," in statement:
            return [{"url": "https://example.com/report", "title": "Report A",
                     "kind": "report", "author": "A. Author", "publisher": "Pub",
                     "publicationDate": "1947-08-15", "description": "Notes"}]
        if "collect(DISTINCT" in statement:
            return [{
                "slug": "project", "id": "project-id", "name": "Project",
                "title": "Project", "description": "Description",
                "clientName": "Client", "objectives": "Objectives",
                "status": "active", "researchQuestion": "Question",
                "domain": "technology", "createdAt": "2026-01-01",
                "updatedAt": "2026-01-02", "findings": [], "sources": [],
            }]
        if "RETURN p.id AS id, p.slug AS slug" in statement:
            return [{"id": parameters.get("id", "existing-id"), "slug": parameters["slug"]}]
        return []


class FindingClient(FakeClient):
    def query(self, statement, parameters=None):
        self.statements.append((statement, parameters))
        if "HAS_EVIDENCE" in statement:
            return [{
                "projectId": "project-id", "sourceId": "source-id",
                "sourceUrl": "https://example.com/report", "sourceTitle": "Report",
                "documentId": "document-id", "claim": "Acme is great", "snippet": "Acme is great.", "confidence": "high", "evidenceId": "ev-id",
                "entityIds": ["entity-id"],
            }]
        if "Finding {" in statement and "RETURN" in statement:
            return [{
                "id": "finding-id", "status": "needs_review", "evidence": [],
                "entities": [], "title": "Finding", "statement": "Statement",
            }]
        return []


class RepositoryTests(unittest.TestCase):
    def setUp(self):
        self.client = FakeClient()
        self.repository = ResearchRepository(self.client)

    def test_create_project_builds_scoped_graph(self):
        result = self.repository.create_project({
                "name": "AI in Healthcare",
                "domain": "technology",
                "researchQuestion": "How is AI changing care?",
            })
        self.assertEqual(result["slug"], "ai-in-healthcare")
        self.assertTrue(result["id"])
        self.assertIn("BELONGS_TO", self.client.statements[0][0])
        self.assertIn("IS_ABOUT", self.client.statements[0][0])

    def test_legacy_project_fields_remain_supported(self):
        self.repository.create_project({
            "title": "Legacy project",
            "domain": "society",
            "keyQuestion": "What changed?",
        })
        self.assertEqual(self.client.statements[0][1]["name"], "Legacy project")

    def test_invalid_domain_and_missing_question_are_rejected(self):
        with self.assertRaises(ValueError):
            self.repository.create_project({"name": "Test", "domain": "invalid", "researchQuestion": "x"})
        with self.assertRaises(ValueError):
            self.repository.create_project({"name": "Test", "domain": "technology"})

    def test_findings_and_sources_are_project_scoped(self):
        self.repository.add_finding("project", {"title": "Evidence", "text": "A useful finding"})
        self.repository.add_source("project", {"title": "Report", "url": "https://example.com/report"})
        self.assertIn("CONCERNS", self.client.statements[0][0])
        self.assertIn("ABOUT", self.client.statements[1][0])

    def test_source_ingestion_persists_document_and_entities(self):
        result = self.repository.add_source("project", {
            "title": "Market report",
            "url": "https://example.com/report",
            "content": "Acme Corporation studies Climate Policy in Europe.",
            "ingest": True,
        })
        self.assertTrue(result["documentId"])
        self.assertGreaterEqual(result["entities"], 1)
        self.assertIn("HAS_DOCUMENT", self.client.statements[0][0])
        self.assertIn("UNWIND $entities", self.client.statements[0][0])

    def test_supplied_document_is_cleaned_before_extraction(self):
        result = self.repository.add_source("project", {
            "title": "Uploaded HTML document",
            "url": "https://example.com/uploaded-document",
            "content": "<nav>Noise</nav><main>Acme Corporation studies Climate Policy in Europe.</main>",
            "ingest": True,
        })
        self.assertEqual(result["status"], "ready")
        self.assertEqual(
            self.client.statements[0][1]["content"],
            "Acme Corporation studies Climate Policy in Europe.",
        )
        self.assertGreaterEqual(result["entities"], 1)

    def test_source_ingestion_records_metadata_evidence_and_status(self):
        self.repository.add_source("project", {
            "title": "Partition report", "url": "https://example.com/report",
            "kind": "report", "author": "Ayesha Khan", "publisher": "Archive Press",
            "publicationDate": "1947-08-15", "description": "Census notes",
            "content": (
                "The committee reported in 1947 that 1.2 million people migrated "
                "to New Delhi. Acme Corporation published the region figures."
            ),
            "ingest": True,
        })
        document, evidence = self.client.statements[0], self.client.statements[1]
        self.assertEqual(document[1]["author"], "Ayesha Khan")
        self.assertEqual(document[1]["kind"], "report")
        self.assertIn("UNWIND $evidence", evidence[0])
        self.assertIn("HAS_EVIDENCE", evidence[0])
        self.assertEqual(evidence[1]["evidence"][0]["confidence"], "high")

    def test_unknown_source_kind_defaults_to_article(self):
        self.repository.add_source("project", {
            "title": "X", "url": "https://example.com/x",
            "content": "Acme Corporation released a statement in 2021.",
            "kind": "interview", "ingest": True,
        })
        self.assertEqual(self.client.statements[0][1]["kind"], "article")

    def test_metadata_only_source_is_registered_pending(self):
        result = self.repository.add_source("project", {
            "title": "Reference", "url": "https://example.com/reference",
            "kind": "government",
        })
        self.assertEqual(result["status"], "pending")
        statement, parameters = self.client.statements[0]
        self.assertIn("ingestionStatus=$status", statement)
        self.assertEqual(parameters["status"], "pending")

    def test_local_document_does_not_require_url(self):
        result = self.repository.add_source("project", {
            "title": "Local document",
            "content": "Acme Corporation studies Climate Policy in Europe.",
            "ingest": True,
        })
        self.assertEqual(result["status"], "ready")
        self.assertEqual(self.client.statements[0][1]["url"], "")
        self.assertTrue(result["id"])

    def test_url_and_document_are_both_accepted(self):
        result = self.repository.add_source("project", {
            "title": "Attributed document",
            "url": "https://example.com/attributed-document",
            "content": "Acme Corporation studies Climate Policy in Europe.",
            "ingest": True,
        })
        self.assertEqual(result["status"], "ready")
        self.assertEqual(
            self.client.statements[0][1]["url"],
            "https://example.com/attributed-document",
        )

    def test_source_requires_url_or_document(self):
        with self.assertRaisesRegex(ValueError, "public URL or a local document"):
            self.repository.add_source("project", {
                "title": "Missing source",
                "ingest": True,
            })

    def test_pdf_document_is_extracted_without_url(self):
        from pypdf import PdfWriter
        writer = PdfWriter()
        writer.add_blank_page(width=200, height=200)
        payload = io.BytesIO()
        writer.write(payload)
        with self.assertRaisesRegex(ValueError, "no readable text"):
            self.repository.add_source("project", {
                "title": "Local PDF",
                "documentBase64": base64.b64encode(payload.getvalue()).decode("ascii"),
                "ingest": True,
            })

    def test_fetch_failure_marks_source_failed_and_never_raises(self):
        from urllib.error import URLError
        with patch("backend.repository.urlopen", side_effect=URLError("refused")):
            result = self.repository.add_source("project", {
                "title": "Unreachable", "url": "https://example.com/unreachable",
                "ingest": True,
            })
        self.assertEqual(result["status"], "failed")
        self.assertTrue(result["warning"])
        marked = [params for _, params in self.client.statements
                  if params and params.get("status") == "failed"]
        self.assertEqual(len(marked), 1)

    def test_reingest_source_reruns_ingestion(self):
        client = FakeClient()
        repository = ResearchRepository(client)
        with patch("backend.repository.urlopen") as mocked:
            mocked.return_value = FakeResponse(
                "<html><body>Acme Corporation announced the Partition Era "
                "migration to New Delhi in 1947.</body></html>"
            )
            result = repository.reingest_source("project", "s1")
        self.assertEqual(result["status"], "ready")
        self.assertTrue(result["documentId"])
        combined = " ".join(statement for statement, _ in client.statements)
        self.assertIn("HAS_EVIDENCE", combined)

    def test_sources_list_supports_filters(self):
        rows = self.repository.sources("project", term="partition", kind="report", status="ready")
        self.assertEqual(len(rows), 2)
        statement, parameters = self.client.statements[0]
        self.assertIn("count(DISTINCT n) AS entities", statement)
        self.assertIn("ingestionStatus", statement)
        self.assertLess(statement.index("WHERE"), statement.index("OPTIONAL MATCH"))
        self.assertEqual(parameters["kind"], "report")
        self.assertEqual(parameters["status"], "ready")
        self.assertIn("partition", parameters["titlePattern"])

    def test_get_source_returns_evidence_and_entities(self):
        source = self.repository.get_source("project", "s1")
        self.assertEqual(source["title"], "Report A")
        self.assertEqual(source["evidence"][0]["confidence"], "high")
        self.assertEqual(source["entities"][0]["type"], "Organization")

    def test_entity_classification_covers_person_event_location(self):
        entities = extract_entities(
            "Professor Ahmed of Acme Corporation explained that the Partition Era "
            "displaced communities to New Delhi in 1947."
        )
        entity_types = {entity["type"] for entity in entities}
        self.assertIn("Organization", entity_types)
        self.assertIn("Person", entity_types)
        self.assertIn("Event", entity_types)
        self.assertIn("Location", entity_types)

    def test_extract_evidence_keeps_paragraph_and_grades_confidence(self):
        evidence = extract_evidence(
            "The committee reported in 1947 that 1.2 million people migrated to "
            "New Delhi. Acme Corporation declined to comment on the census.",
            "https://example.com/report",
        )
        self.assertGreaterEqual(len(evidence), 1)
        self.assertEqual(evidence[0]["confidence"], "high")
        self.assertEqual(evidence[0]["location"], "sentence:1")

    def test_entity_extraction_is_bounded_and_deterministic(self):
        first = extract_entities("Acme Corporation works on Climate Policy.")
        second = extract_entities("Acme Corporation works on Climate Policy.")
        self.assertEqual(first, second)
        self.assertEqual(first[0]["type"], "Organization")

    def test_html_cleaning_removes_navigation_and_scripts(self):
        cleaned = clean_content("<nav>Menu</nav><script>noise()</script><main>OpenAI research</main>")
        self.assertEqual(cleaned, "OpenAI research")

    def test_finding_generation_is_evidence_first_and_deterministic(self):
        client = FindingClient()
        result = ResearchRepository(client).generate_findings("project")
        self.assertEqual(result["count"], 1)
        self.assertIn("SUPPORTED_BY", client.statements[1][0])
        self.assertEqual(result["generated"][0]["status"], "needs_review")

    def test_slug_requires_meaningful_input(self):
        with self.assertRaises(ValueError):
            slugify("!!!")

    def test_bolt_uri_is_normalized_for_http_transaction_api(self):
        self.assertEqual(http_uri("neo4j://127.0.0.1:7687"), "http://127.0.0.1:7474")

    def test_status_and_objectives_are_persisted(self):
        self.repository.create_project({
            "name": "Climate Signals",
            "clientName": "Acme",
            "domain": "environment",
            "researchQuestion": "What changes?",
            "objectives": "Compare markets",
            "status": "active",
        })
        parameters = self.client.statements[0][1]
        self.assertEqual(parameters["clientName"], "Acme")
        self.assertEqual(parameters["objectives"], "Compare markets")
        self.assertEqual(parameters["status"], "active")

    def test_project_retrieval_returns_workspace_metadata(self):
        project = self.repository.get_project("project")
        self.assertEqual(project["clientName"], "Client")
        self.assertEqual(project["objectives"], "Objectives")
        self.assertEqual(project["activity"][0]["type"], "updated")

    def test_project_report_builds_summary_from_real_project_data(self):
        report = self.repository.project_report("project")
        self.assertEqual(report["metrics"]["sources"], 0)
        self.assertEqual(report["metrics"]["findings"], 0)
        self.assertIn("Research question", report["summary"])
        self.assertEqual(report["projectSlug"], "project")

    def test_finding_persists_evidence_and_confidence(self):
        finding_id = self.repository.add_finding("project", {
            "title": "Observed pattern",
            "text": "The source reports a measurable change.",
            "source": "https://example.com/report",
            "confidence": "high",
        })
        self.assertTrue(finding_id)
        statement, parameters = self.client.statements[0]
        self.assertIn("Evidence", statement)
        self.assertEqual(parameters["confidence"], "high")

    def test_new_findings_default_to_draft_status(self):
        self.repository.add_finding("project", {
            "title": "Draft finding",
            "text": "Draft text",
        })
        statement, _ = self.client.statements[0]
        self.assertIn("coalesce(f.status,'draft')", statement)


if __name__ == "__main__":
    unittest.main()
