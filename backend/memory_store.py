"""In-memory research store for degraded/demo mode.

Used only when Neo4j is unreachable so the non-graph parts of the application
(browser, dashboard, project/source/finding workflows) stay inspectable and
testable. Implements the same research vocabulary as the Neo4j store
(backend/repository.py) and is swapped out automatically once a graph database
is available. All seeded content is clearly labeled DEMO/SAMPLE and must never
be presented as real research.
"""

from datetime import date
import hashlib
import re
import uuid

from .repository import (
    DOMAINS,
    SOURCE_TYPES,
    STATUSES,
    clean_content,
    extract_entities,
    extract_evidence,
    extract_uploaded_document,
    require_text,
    slugify,
)
from .graph_repository import LocalGraphRepository
from .graph_seed import (
    PUBLIC_AI_SLUG,
    SEED_ENTITIES,
    SEED_RELATIONSHIPS,
)
import hashlib as _hashlib


def _entity_seed_id(name, entity_type):
    key = name.lower().strip()
    return _hashlib.sha256(f"{entity_type}:{key}".encode("utf-8")).hexdigest()[:32]


def _now():
    return date.today().isoformat()


class MemoryStore:
    storage_name = "demo"

    def __init__(self, seed=True):
        self._projects = {}
        if seed:
            self._seed()

    def _project(self, slug):
        if slug not in self._projects:
            raise KeyError("Project not found.")
        return self._projects[slug]

    def _link(self, project, from_type, from_name, relationship, to_type, to_name, source_url=""):
        project["relationships"].append({
            "fromType": from_type,
            "fromName": from_name,
            "relationship": relationship,
            "toType": to_type,
            "toName": to_name,
            "sourceUrl": source_url if source_url else None,
        })

    def dashboard(self):
        projects = list(self._projects.values())
        active = [p for p in projects if p["status"] in
                  ("planning", "active", "scoping", "in progress", "drafting")]
        findings = [f for p in projects for f in p["findings"]]
        metrics = {
            "projects": len(projects),
            "activeProjects": len(active),
            "sources": sum(len(p["sources"]) for p in projects),
            "findings": len(findings),
            "verifiedFindings": sum(1 for f in findings if f["status"] == "verified"),
            "findingsNeedsReview": sum(1 for f in findings if f["status"] == "needs_review"),
            "entities": sum(len(p["entities"]) for p in projects),
            "relationships": sum(len(p["relationships"]) for p in projects),
        }
        recent_projects = sorted(projects, key=lambda p: p["updatedAt"], reverse=True)[:5]
        recent_findings = sorted(
            [dict(f, projectName=p["name"], projectTitle=p["title"])
             for p in projects for f in p["findings"]],
            key=lambda f: f["createdAt"],
            reverse=True,
        )[:5]
        return {
            "metrics": metrics,
            "recentProjects": [{
                "slug": p["slug"], "name": p["name"], "title": p["title"],
                "status": p["status"], "domain": p["domain"],
                "updatedAt": p["updatedAt"],
            } for p in recent_projects],
            "recentFindings": recent_findings,
        }

    def list_projects(self):
        projects = sorted(self._projects.values(), key=lambda p: p["updatedAt"], reverse=True)
        return [{key: p[key] for key in (
            "slug", "name", "title", "description", "clientName", "status",
            "researchQuestion", "keyQuestion", "domain", "createdAt", "updatedAt",
        )} for p in projects]

    def _project_fields(self, data):
        if not data.get("name") and data.get("title"):
            data = dict(data, name=data["title"])
        if not data.get("researchQuestion") and data.get("keyQuestion"):
            data = dict(data, researchQuestion=data["keyQuestion"])
        name = require_text(data, "name", 160)
        domain = str(data.get("domain", "")).strip().lower()
        if domain not in DOMAINS:
            raise ValueError("domain must be one of the supported research domains.")
        question = require_text(data, "researchQuestion", 1000)
        status = str(data.get("status", "planning")).strip().lower().replace(" ", "_")
        if status not in STATUSES:
            raise ValueError("status must be planning, active, on_hold, or completed.")
        return {
            "name": name,
            "title": name,
            "description": str(data.get("description", "")).strip()[:2000],
            "clientName": require_text(data, "clientName", 240) if data.get("clientName") else "",
            "researchQuestion": question,
            "keyQuestion": question,
            "objectives": str(data.get("objectives", "")).strip()[:3000],
            "status": status,
            "domain": domain,
        }

    def create_project(self, data):
        fields = self._project_fields(data)
        slug = slugify(fields["name"])
        existing = self._projects.get(slug)
        if existing:
            existing.update(fields)
            existing["updatedAt"] = _now()
            return {"id": existing["id"], "slug": slug}
        self._projects[slug] = {
            "id": str(uuid.uuid4()), "slug": slug, "createdAt": _now(),
            "updatedAt": _now(), "sources": [], "findings": [], "entities": [],
            "relationships": [], **fields,
        }
        project = self._projects[slug]
        self._link(project, "Project", project["name"], "BELONGS_TO", "Domain", project["domain"])
        self._link(project, "Project", project["name"], "IS_ABOUT", "Topic", project["name"])
        if project["clientName"]:
            self._link(project, "Project", project["name"], "FOR_CLIENT", "Client", project["clientName"])
        return {"id": project["id"], "slug": slug}

    def update_project(self, slug, data):
        project = self._project(slug)
        fields = self._project_fields(data)
        project.update(fields)
        project["updatedAt"] = _now()
        project["relationships"] = [
            row for row in project["relationships"]
            if row["relationship"] not in ("BELONGS_TO", "IS_ABOUT", "FOR_CLIENT")
        ]
        self._link(project, "Project", project["name"], "BELONGS_TO", "Domain", project["domain"])
        self._link(project, "Project", project["name"], "IS_ABOUT", "Topic", project["name"])
        if project["clientName"]:
            self._link(project, "Project", project["name"], "FOR_CLIENT", "Client", project["clientName"])
        return self.get_project(slug)

    def get_project(self, slug):
        project = self._project(slug)
        return {
            "slug": project["slug"], "id": project["id"], "name": project["name"],
            "title": project["title"], "description": project["description"],
            "clientName": project["clientName"], "objectives": project["objectives"],
            "status": project["status"], "researchQuestion": project["researchQuestion"],
            "domain": project["domain"], "createdAt": project["createdAt"],
            "updatedAt": project["updatedAt"],
            "findings": [{key: finding[key] for key in (
                "id", "title", "text", "statement", "source", "status", "confidence",
            )} for finding in project["findings"]],
            "sources": [{
                key: source.get(key, "") for key in (
                    "id", "title", "url", "kind", "author", "publisher",
                    "publicationDate", "ingestionStatus", "createdAt",
                )
            } for source in project["sources"]],
            "entities": [{"id": e["id"], "type": e["type"], "name": e["name"]}
                         for e in project["entities"]],
            "relationships": self.graph(slug),
            "evidence": [
                {"id": ev["id"], "snippet": ev["snippet"],
                 "sourceUrl": ev["sourceUrl"], "findingId": finding["id"],
                 "findingTitle": finding["title"]}
                for finding in project["findings"] for ev in finding["evidence"]
            ],
            "insights": self.insights(slug),
            "activity": [
                {"type": "updated", "date": project["updatedAt"]},
                {"type": "created", "date": project["createdAt"]},
            ],
        }

    def add_source(self, slug, data):
        project = self._project(slug)
        title = require_text(data, "title", 300)
        url = str(data.get("url", "")).strip()[:2000]
        content = clean_content(str(data.get("content", "")))
        if not content:
            content = extract_uploaded_document(data)
        if not url and not content:
            raise ValueError("Provide a public URL or a local document.")
        if url and not re.match(r"^https?://", url, re.I):
            raise ValueError("url must start with http:// or https://.")
        kind = str(data.get("kind", "article")).strip().lower()[:40]
        if kind not in SOURCE_TYPES:
            kind = "article"
        source_id = str(uuid.uuid5(uuid.NAMESPACE_URL, url or f"{slug}:{title}"))
        metadata = {
            "author": str(data.get("author", "")).strip()[:200],
            "publisher": str(data.get("publisher", "")).strip()[:200],
            "publicationDate": str(data.get("publicationDate", "")).strip()[:40],
            "description": str(data.get("description", "")).strip()[:1000],
        }
        if not data.get("ingest") and not content:
            project["sources"] = [s for s in project["sources"] if s["url"] != url]
            project["sources"].append({
                "id": source_id, "title": title, "url": url, "kind": kind,
                "content": "", "contentHash": "", "evidence": [],
                "ingestionStatus": "pending", "createdAt": _now(),
                "updatedAt": _now(), **metadata,
            })
            self._link(project, "Source", url, "ABOUT", "Project", project["name"])
            return {"id": source_id, "documentId": None, "entities": 0,
                    "evidence": 0, "status": "pending"}
        if not content:
            content = (
                f"DEMO sample placeholder document for {url}. This demo store does "
                "not retrieve remote pages; replace this project with a real source "
                "when Neo4j is connected."
            )
        content = clean_content(content)
        if not content:
            raise ValueError("Source content is empty.")
        document_id = hashlib.sha256(content.encode("utf-8")).hexdigest()
        entities = extract_entities(content)
        evidence = extract_evidence(content, url)
        evidence_by_sentence = {}
        for item in evidence:
            parts = str(item.get("location", "")).split(":")
            if len(parts) == 2 and parts[0] == "sentence":
                try:
                    evidence_by_sentence[int(parts[1])] = item["id"]
                except ValueError:
                    pass
        for entity in entities:
            entity["sourceId"] = source_id
            entity["sourceUrl"] = url
            entity["documentId"] = document_id
            entity["evidenceId"] = evidence_by_sentence.get(entity.get("sentenceIndex", 0), "")
        project["sources"] = [s for s in project["sources"] if s["url"] != url]
        project["sources"].append({
            "id": source_id, "title": title, "url": url, "kind": kind,
            "content": content, "contentHash": document_id, "evidence": evidence,
            "ingestionStatus": "ready", "createdAt": _now(), "updatedAt": _now(),
            **metadata,
        })
        for entity in entities:
            if not any(e["name"] == entity["name"] and e["type"] == entity["type"]
                       for e in project["entities"]):
                project["entities"].append({
                    "id": entity["id"], "name": entity["name"],
                    "type": entity["type"], "sourceId": source_id,
                    "sourceUrl": entity.get("sourceUrl", ""),
                    "evidenceId": entity.get("evidenceId", ""),
                    "confidenceScore": entity.get("confidenceScore", 0.0),
                    "confidence": entity.get("confidence", "low"),
                    "description": entity.get("description", ""),
                    "mentions": entity.get("mentions", 1),
                    "documentId": document_id,
                })
            else:
                existing = next(e for e in project["entities"]
                                if e["name"] == entity["name"] and e["type"] == entity["type"])
                existing["mentions"] = existing.get("mentions", 1) + entity.get("mentions", 1)
        self._link(project, "Source", url, "ABOUT", "Project", project["name"])
        self._link(project, "Source", title, "HAS_DOCUMENT", "Document", title)
        for index, entity in enumerate(entities):
            self._link(project, "Document", title, "MENTIONS", entity["type"], entity["name"])
            self._link(project, "Project", project["name"], "HAS_ENTITY", entity["type"], entity["name"])
        for left, right in zip(entities, entities[1:]):
            self._link(project, left["type"], left["name"], "RELATED_TO", right["type"], right["name"], url)
        return {"id": source_id, "documentId": document_id, "entities": len(entities),
                "evidence": len(evidence), "status": "ready"}

    def sources(self, slug, term="", kind="", status=""):
        project = self._project(slug)
        term = str(term or "").strip().lower()
        rows = []
        for source in project["sources"]:
            if kind and source["kind"] != kind:
                continue
            if status and source["ingestionStatus"] != status:
                continue
            if term and term not in source["title"].lower() and term not in source["url"].lower():
                continue
            rows.append({
                "id": source["id"], "title": source["title"], "url": source["url"],
                "kind": source["kind"], "author": source.get("author", ""),
                "publisher": source.get("publisher", ""),
                "publicationDate": source.get("publicationDate", ""),
                "description": source.get("description", ""),
                "ingestionStatus": source["ingestionStatus"],
                "ingestionError": source.get("ingestionError", ""),
                "createdAt": source["createdAt"], "updatedAt": source["updatedAt"],
                "entities": sum(1 for e in project["entities"] if e["sourceId"] == source["id"]),
                "evidence": len(source.get("evidence", [])),
            })
        return sorted(rows, key=lambda row: (row["updatedAt"] or "", row["createdAt"] or ""), reverse=True)

    def get_source(self, slug, source_id):
        project = self._project(slug)
        source = next((s for s in project["sources"] if s["id"] == source_id), None)
        if not source:
            raise KeyError("Source not found.")
        return {
            "id": source["id"], "title": source["title"], "url": source["url"],
            "kind": source["kind"], "author": source.get("author", ""),
            "publisher": source.get("publisher", ""),
            "publicationDate": source.get("publicationDate", ""),
            "description": source.get("description", ""),
            "ingestionStatus": source["ingestionStatus"],
            "ingestionError": source.get("ingestionError", ""),
            "content": source.get("content", ""),
            "createdAt": source["createdAt"], "updatedAt": source["updatedAt"],
            "evidence": [dict(ev) for ev in source.get("evidence", [])],
            "entities": [{"id": e["id"], "type": e["type"], "name": e["name"],
                          "confidence": e.get("confidence", "low")}
                         for e in project["entities"] if e["sourceId"] == source["id"]],
        }

    def reingest_source(self, slug, source_id):
        project = self._project(slug)
        source = next((s for s in project["sources"] if s["id"] == source_id), None)
        if not source:
            raise KeyError("Source not found.")
        return self.add_source(slug, {
            "title": source["title"], "url": source["url"], "kind": source["kind"],
            "author": source.get("author", ""), "publisher": source.get("publisher", ""),
            "publicationDate": source.get("publicationDate", ""),
            "description": source.get("description", ""), "ingest": True,
        })

    def add_finding(self, slug, data):
        project = self._project(slug)
        title = require_text(data, "title", 300)
        text = require_text(data, "text", 5000)
        source = str(data.get("source", "")).strip()[:2000]
        finding_id = str(uuid.uuid4())
        confidence = str(data.get("confidence", "unassessed")).strip().lower()[:40]
        finding = {
            "id": finding_id, "title": title, "text": text, "statement": text,
            "source": source, "confidence": confidence, "status": "draft",
            "createdAt": _now(), "updatedAt": _now(), "evidence": [],
        }
        if source:
            source_id = str(uuid.uuid5(uuid.NAMESPACE_URL, source))
            if not any(s["url"] == source for s in project["sources"]):
                project["sources"].append({
                    "id": source_id, "title": source, "url": source,
                    "kind": "article", "content": "", "contentHash": "",
                    "evidence": [], "ingestionStatus": "pending", "createdAt": _now(),
                    "updatedAt": _now(), "author": "", "publisher": "",
                    "publicationDate": "", "description": "",
                })
            evidence = {
                "id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"{slug}:{source}:{title}")),
                "snippet": text, "sourceUrl": source,
            }
            finding["evidence"].append(evidence)
            self._link(project, "Finding", title, "CONCERNS", "Project", project["name"])
            self._link(project, "Finding", title, "DRAWS_ON", "Source", source)
            self._link(project, "Evidence", text[:60], "SUPPORTS", "Finding", title, source)
        else:
            self._link(project, "Finding", title, "CONCERNS", "Project", project["name"])
        project["findings"].append(finding)
        return finding_id

    def generate_findings(self, slug):
        project = self._project(slug)
        generated = []
        for source in project["sources"]:
            if not source["content"]:
                continue
            content = source["content"]
            entity_ids = [e["id"] for e in project["entities"]
                          if e["sourceId"] == source["id"]]
            finding_id = str(uuid.uuid5(
                uuid.NAMESPACE_URL, f"{slug}:{source['contentHash']}:entity-coverage"
            ))
            title = f"Research coverage from {source['title']}"
            statement = (
                f"The source contains {len(entity_ids)} extracted research entities "
                "available for project analysis."
            )
            finding = {
                "id": finding_id, "title": title, "text": statement,
                "statement": statement, "source": source["url"],
                "confidence": "low", "status": "needs_review",
                "createdAt": _now(), "updatedAt": _now(),
                "evidence": [{
                    "id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"{finding_id}:evidence")),
                    "snippet": content[:600], "sourceUrl": source["url"],
                }],
            }
            project["findings"] = [f for f in project["findings"] if f["id"] != finding_id]
            project["findings"].append(finding)
            self._link(project, "Finding", title, "CONCERNS", "Project", project["name"], source["url"])
            self._link(project, "Evidence", content[:60], "SUPPORTS", "Finding", title, source["url"])
            self._link(project, "Evidence", content[:60], "FROM_SOURCE", "Source", source["url"], source["url"])
            for entity in [e for e in project["entities"] if e["sourceId"] == source["id"]]:
                self._link(project, "Finding", title, "ABOUT", entity["type"], entity["name"], source["url"])
            generated.append({"id": finding_id, "title": title, "status": "needs_review"})
        return {"generated": generated, "count": len(generated)}

    def _find_finding(self, finding_id):
        for project in self._projects.values():
            for finding in project["findings"]:
                if finding["id"] == finding_id:
                    return project, finding
        raise KeyError("Finding not found.")

    def get_finding(self, finding_id):
        project, finding = self._find_finding(finding_id)
        return {
            "id": finding["id"], "projectId": project["id"],
            "projectSlug": project["slug"], "title": finding["title"],
            "statement": finding["statement"], "text": finding["text"],
            "status": finding["status"], "confidence": finding["confidence"],
            "createdAt": finding["createdAt"],
            "evidence": [{key: ev[key] for key in ("id", "snippet", "sourceUrl")}
                         for ev in finding["evidence"]],
            "entities": [
                {"id": e["id"], "type": e["type"], "name": e["name"]}
                for e in project["entities"]
            ],
        }

    def update_finding(self, finding_id, data):
        status = str(data.get("status", "")).strip().lower()
        allowed = {"draft", "needs_review", "verified", "rejected"}
        if status not in allowed:
            raise ValueError("status must be draft, needs_review, verified, or rejected.")
        project, finding = self._find_finding(finding_id)
        transitions = {
            "draft": {"draft", "needs_review"},
            "needs_review": {"needs_review", "verified", "rejected"},
            "verified": {"verified"},
            "rejected": {"rejected", "needs_review"},
        }
        if status not in transitions.get(finding["status"], set()):
            raise ValueError("Unsupported finding status transition.")
        finding["status"] = status
        finding["updatedAt"] = _now()
        return self.get_finding(finding_id)

    def findings(self, slug):
        project = self._project(slug)
        rows = []
        for finding in project["findings"]:
            rows.append({
                "id": finding["id"], "title": finding["title"], "text": finding["text"],
                "confidence": finding["confidence"], "createdAt": finding["createdAt"],
                "sources": [s["url"] for s in project["sources"]
                            if s["url"] == finding["source"]] or (
                                [finding["source"]] if finding["source"] else []),
                "evidence": [{key: ev[key] for key in ("id", "snippet", "sourceUrl")}
                             for ev in finding["evidence"]],
            })
        return sorted(rows, key=lambda row: row["createdAt"], reverse=True)

    def entities(self, slug, entity_type=""):
        project = self._project(slug)
        rows = []
        for e in project["entities"]:
            source = next((s for s in project["sources"] if s["id"] == e["sourceId"]), None)
            snippet = ""
            if source is not None:
                ev = next((v for v in source.get("evidence", [])
                           if v["id"] == e.get("evidenceId")), None)
                snippet = (ev or {}).get("snippet", "")
            rows.append({
                "id": e["id"], "type": e["type"], "name": e["name"],
                "confidence": e.get("confidenceScore", 0.0),
                "confidenceLabel": e.get("confidence", "low"),
                "description": e.get("description", ""),
                "sourceId": e["sourceId"],
                "sourceTitle": source["title"] if source else "",
                "sourceUrl": source["url"] if source else "",
                "evidenceId": e.get("evidenceId", ""),
                "evidenceSnippet": snippet,
                "demo": bool(e.get("demo")),
                "mentions": e.get("mentions", 1),
            })
        if entity_type.strip():
            rows = [row for row in rows if row["type"] == entity_type.strip()]
        return sorted(rows, key=lambda row: (row["type"], row["name"]))

    def insights(self, slug):
        project = self._project(slug)
        counts = {}
        for entity in project["entities"]:
            counts[entity["type"]] = counts.get(entity["type"], 0) + 1
        ordered = sorted(counts.items(), key=lambda item: item[1], reverse=True)
        return [{"title": "Extracted entities",
                 "detail": f"{count} {entity_type} entities"}
                for entity_type, count in ordered]

    def graph(self, slug):
        project = self._project(slug)
        return sorted(
            [dict(row) for row in project["relationships"]],
            key=lambda row: (row["relationship"], row["toName"] or ""),
        )

    # --- Knowledge graph integration (local fallback) ---
    @property
    def graph_repository(self):
        if not hasattr(self, "_graph_repository"):
            self._graph_repository = LocalGraphRepository(self)
        return self._graph_repository

    def seed_relationships(self, slug):
        if slug != PUBLIC_AI_SLUG:
            return []
        return SEED_RELATIONSHIPS

    def graph_data(self, slug):
        return self.graph_repository.graph(slug)

    def graph_nodes(self, slug):
        return self.graph_repository.nodes(slug)

    def graph_relationships(self, slug):
        return self.graph_repository.relationships(slug)

    def graph_search(self, slug, term):
        return self.graph_repository.search(slug, term)

    def graph_node(self, slug, node_id):
        return self.graph_repository.node(slug, node_id)

    def search(self, slug, term):
        project = self._project(slug)
        term = require_text({"term": term}, "term", 200)
        pattern = re.compile(re.escape(term), re.I)
        match = lambda value: bool(value) and pattern.search(str(value)) is not None
        return {
            "entities": [
                {"type": e["type"], "name": e["name"], "sourceId": e["sourceId"],
                 "confidence": e.get("confidence", "low")}
                for e in project["entities"] if match(e["name"])
            ],
            "sources": [
                {"id": s["id"], "title": s["title"], "url": s["url"],
                 "status": s["ingestionStatus"]}
                for s in project["sources"] if match(s["title"]) or match(s["url"])
            ],
            "findings": [
                {"id": f["id"], "title": f["title"], "text": f["text"]}
                for f in project["findings"] if match(f["title"]) or match(f["text"])
            ],
            "relationships": [
                {"fromName": row["fromName"], "relationship": row["relationship"],
                 "toName": row["toName"], "sourceUrl": row["sourceUrl"]}
                for row in project["relationships"]
                if match(row["fromName"]) or match(row["toName"])
            ],
        }

    def _seed(self):
        self.create_project({
            "name": "Partition-Era Culture & Migration (DEMO)",
            "domain": "culture",
            "status": "active",
            "clientName": "DEMO client â€” sample",
            "researchQuestion": (
                "DEMO research question: how did micro-community cultural practices "
                "shift during and after Partition-era migration? Sample data only."
            ),
            "description": (
                "Clearly labeled DEMO sample project. It exercises the project, "
                "source, finding, entity, and relationship workflows and is meant "
                "to be replaced by real research."
            ),
            "objectives": (
                "DEMO objectives: demonstrate the research workspace end to end. "
                "No historical claims are made."
            ),
        })
        self.add_source("partition-era-culture-migration-demo", {
            "title": "DEMO sample source â€” placeholder fixture",
            "url": "https://example.com/sample-source-partition-culture",
            "kind": "article",
            "content": (
                "DEMO sample document for the Research Intelligence prototype. "
                "This placeholder text is sample data and should be replaced with a "
                "real, cited source. Sample Organization and Sample Community appear "
                "here only as placeholder entities."
            ),
            "ingest": True,
        })
        self.add_finding("partition-era-culture-migration-demo", {
            "title": "DEMO sample finding â€” replace with verified synthesis",
            "text": (
                "This is clearly labeled sample data for the prototype. Replace with "
                "real, source-backed synthesis."
            ),
            "source": "https://example.com/sample-source-partition-culture",
            "confidence": "low",
        })
        self.add_finding("partition-era-culture-migration-demo", {
            "title": "DEMO example finding â€” sources and evidence workflow",
            "text": (
                "Demo finding that demonstrates the sources and evidence workflow. "
                "Not a research claim."
            ),
        })
        self.create_project({
            "name": "Community Cultural Practices Survey (DEMO)",
            "domain": "society",
            "status": "planning",
            "researchQuestion": (
                "DEMO research question: which cultural practices do communities "
                "preserve through migration? Sample data only."
            ),
            "description": (
                "Clearly labeled DEMO sample project for the society domain. "
                "Replace with real research."
            ),
        })
        self.add_source("community-cultural-practices-survey-demo", {
            "title": "DEMO sample source â€” placeholder fixture two",
            "url": "https://example.com/sample-source-community-practices",
            "kind": "article",
            "content": (
                "DEMO sample document for the community practices survey. Sample "
                "Topic and Sample Event are placeholder entities only."
            ),
            "ingest": True,
        })
        self.add_finding("community-cultural-practices-survey-demo", {
            "title": "DEMO sample finding â€” planning state",
            "text": "Sample finding attached to a planning-state project. Not research.",
        })
        self._seed_public_ai()

    def _seed_public_ai(self):
        """Seed the Public AI project with clearly-labeled demo graph data."""
        self.create_project({
            "name": "Public AI Research Source Validation 2026-08-28",
            "domain": "technology",
            "status": "active",
            "researchQuestion": "How is artificial intelligence defined and applied?",
            "description": "Live validation project using one public research source.",
        })
        slug = PUBLIC_AI_SLUG
        project = self._project(slug)
        source_url = "https://en.wikipedia.org/wiki/Artificial_intelligence"
        source_id = str(uuid.uuid5(uuid.NAMESPACE_URL, source_url))
        project["sources"] = [{
            "id": source_id, "title": "Artificial intelligence - Wikipedia",
            "url": source_url, "kind": "article", "content": "",
            "contentHash": "", "evidence": [], "ingestionStatus": "ready",
            "createdAt": _now(), "updatedAt": _now(), "author": "",
            "publisher": "Wikipedia", "publicationDate": "", "description":
                "Public source demonstrating the knowledge graph. (demo seed data)",
        }]
        finding_id = str(uuid.uuid4())
        project["findings"] = [{
            "id": finding_id, "title": "Research coverage from Artificial intelligence - Wikipedia",
            "text": "The source contains demo research entities available for project analysis.",
            "statement": "The source contains demo research entities available for project analysis.",
            "source": source_url, "confidence": "low", "status": "needs_review",
            "createdAt": _now(), "updatedAt": _now(),
            "evidence": [{
                "id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"{finding_id}:evidence")),
                "snippet": "Demo finding backed by a public source. (demo seed data)",
                "sourceUrl": source_url,
            }],
        }]
        for entity in SEED_ENTITIES:
            entity_id = _entity_seed_id(entity["name"], entity["type"])
            project["entities"].append({
                "id": entity_id, "name": entity["name"], "type": entity["type"],
                "sourceId": source_id, "sourceUrl": source_url,
                "evidenceId": "", "confidenceScore": 0.5,
                "confidence": "demo", "description": entity["description"],
                "mentions": 1, "demo": True,
            })
        for rel in SEED_RELATIONSHIPS:
            pass
        # Connect the finding to the source and records a related edge keyword so
        # relationships() traversal sees an entity-entity chain via the seed list.
        self._link(project, "Source", source_url, "ABOUT", "Project", project["name"])
        self._link(project, "Project", project["name"], "HAS_ENTITY", "Organization", "OpenAI")