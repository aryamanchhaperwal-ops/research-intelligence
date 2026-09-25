import base64
import io
import re
import uuid
import hashlib
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from datetime import date

from .neo4j_client import Neo4jClient


DOMAINS = ("technology", "society", "environment", "esg", "culture", "business", "other")
STATUSES = ("planning", "active", "on_hold", "completed", "archived", "scoping", "in progress", "drafting", "complete")


def slugify(value):
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    if not slug:
        raise ValueError("A project name must contain letters or numbers.")
    return slug[:80]


def require_text(data, field, maximum=500):
    value = str(data.get(field, "")).strip()
    if not value:
        raise ValueError(f"{field} is required.")
    if len(value) > maximum:
        raise ValueError(f"{field} must be {maximum} characters or fewer.")
    return value


from .extraction import (
    classify_entity,
    extract_entities,
    is_meaningless_entity,
    canonicalize_name,
)
from .graph_repository import Neo4jGraphRepository
from .graph_seed import PUBLIC_AI_SLUG, SEED_ENTITIES, SEED_RELATIONSHIPS

SOURCE_TYPES = {
    "article", "research-paper", "report", "dataset", "government",
    "organization", "web-page", "other",
}
EVIDENCE_INDICATORS = re.compile(
    r"\b(according to|said|found that|showed that|shows that|reported|"
    r"stated that|argued|noted that|suggest(s|ed)? that|indicates|indicated|"
    r"evidence|documented|described|explains|explained|because|reveals|"
    r"revealed|concluded|confirmed|estimates? that)\b", re.I
)
YEAR_PATTERN = re.compile(r"\b(?:1[5-9]\d{2}|20\d{2})\b")


def extract_uploaded_document(data):
    encoded = str(data.get("documentBase64", "")).strip()
    if not encoded:
        return ""
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (ValueError, TypeError, base64.binascii.Error) as error:
        raise ValueError("The uploaded document is not valid base64 data.") from error
    try:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(raw))
        content = clean_content("\n".join(page.extract_text() or "" for page in reader.pages))
        if not content:
            raise ValueError("The PDF contains no readable text.")
        return content
    except Exception as error:
        if isinstance(error, ValueError) and str(error) == "The PDF contains no readable text.":
            raise
        raise ValueError("The PDF could not be read. Please upload a readable PDF.") from error


def _split_sentences(content):
    return [sentence.strip() for sentence in re.split(r"(?<=[.!?])\s+", content) if sentence.strip()]


def _evidence_confidence(sentence):
    has_year = YEAR_PATTERN.search(sentence)
    has_quantity = re.search(r"\d[\d,\.]*(%| million| billion| thousand| people| years| families| villages| per cent)", sentence, re.I)
    proper_count = len(re.findall(r"\b[A-Z][a-z]+\b", sentence))
    if has_year and (has_quantity or proper_count >= 3):
        return "high"
    if has_year or has_quantity:
        return "medium"
    if proper_count >= 3:
        return "medium"
    return "low"


def extract_evidence(content, source_key, limit=12, minimum_length=60):
    evidence = []
    seen = set()
    for index, sentence in enumerate(_split_sentences(content), start=1):
        if len(sentence) < minimum_length:
            continue
        has_indicator = EVIDENCE_INDICATORS.search(sentence)
        proper_count = len(re.findall(r"\b[A-Z][a-z]+\b", sentence))
        if not (has_indicator or YEAR_PATTERN.search(sentence) or proper_count >= 3):
            continue
        claim = sentence[:180].rsplit(" ", 1)[0] if len(sentence) > 180 else sentence
        item_key = claim.lower()[:80]
        if item_key in seen:
            continue
        seen.add(item_key)
        item_id = hashlib.sha256(f"{source_key}:{index}:{claim[:80].lower()}".encode()).hexdigest()[:24]
        evidence.append({
            "id": item_id,
            "claim": claim,
            "excerpt": sentence,
            "location": f"sentence:{index}",
            "confidence": _evidence_confidence(sentence),
            "status": "extracted",
        })
        if len(evidence) >= limit:
            break
    return evidence


class _ResearchTextParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "nav", "header", "footer", "aside", "form"}:
            self.skip_depth += 1

    def handle_endtag(self, tag):
        if tag in {"script", "style", "nav", "header", "footer", "aside", "form"} and self.skip_depth:
            self.skip_depth -= 1

    def handle_data(self, data):
        if not self.skip_depth:
            value = re.sub(r"\s+", " ", data).strip()
            if value:
                self.parts.append(value)


def clean_content(content):
    parser = _ResearchTextParser()
    parser.feed(content)
    return re.sub(r"\s+", " ", " ".join(parser.parts)).strip()


class ResearchRepository:
    storage_name = "neo4j"

    def __init__(self, client: Neo4jClient):
        self.client = client

    def dashboard(self):
        rows = self.client.query(
            "CALL { MATCH (p:Project) RETURN count(p) AS projects } "
            "CALL { MATCH (p:Project) WHERE p.status IN ['planning','active','scoping','in progress','drafting'] "
            "RETURN count(p) AS activeProjects } "
            "CALL { MATCH (s:Source) RETURN count(s) AS sources } "
            "CALL { MATCH (f:Finding) RETURN count(f) AS findings } "
            "CALL { MATCH (f:Finding) WHERE f.status='verified' RETURN count(f) AS verifiedFindings } "
            "CALL { MATCH (f:Finding) WHERE f.status='needs_review' RETURN count(f) AS findingsNeedsReview } "
            "CALL { MATCH (n) WHERE NOT n:Domain RETURN count(n) AS entities } "
            "CALL { MATCH ()-[r]->() RETURN count(r) AS relationships } "
            "RETURN projects, activeProjects, sources, findings, verifiedFindings, "
            "findingsNeedsReview, entities, relationships"
        )
        metrics = rows[0] if rows else {
            "projects": 0, "activeProjects": 0, "sources": 0, "findings": 0,
            "verifiedFindings": 0, "findingsNeedsReview": 0, "entities": 0,
            "relationships": 0,
        }
        recent_projects = self.client.query(
            "MATCH (p:Project)-[:BELONGS_TO]->(d:Domain) "
            "RETURN p.slug AS slug, p.name AS name, p.title AS title, "
            "p.status AS status, d.name AS domain, p.updatedAt AS updatedAt "
            "ORDER BY p.updatedAt DESC LIMIT 5"
        )
        recent_findings = self.client.query(
            "MATCH (f:Finding)-[:CONCERNS]->(p:Project) "
            "RETURN f.id AS id, f.title AS title, f.createdAt AS createdAt, "
            "p.name AS projectName, p.title AS projectTitle "
            "ORDER BY f.createdAt DESC LIMIT 5"
        )
        return {"metrics": metrics, "recentProjects": recent_projects,
                "recentFindings": recent_findings}

    def list_projects(self):
        return self.client.query(
            "MATCH (p:Project)-[:BELONGS_TO]->(d:Domain) "
            "RETURN p.slug AS slug, p.name AS name, p.title AS title, "
            "p.description AS description, p.clientName AS clientName, p.status AS status, "
            "p.researchQuestion AS researchQuestion, p.keyQuestion AS keyQuestion, "
            "d.name AS domain, p.createdAt AS createdAt, p.updatedAt AS updatedAt "
            "ORDER BY p.updatedAt DESC"
        )

    def create_project(self, data):
        if not data.get("name") and data.get("title"):
            data = dict(data, name=data["title"])
        if not data.get("researchQuestion") and data.get("keyQuestion"):
            data = dict(data, researchQuestion=data["keyQuestion"])
        name = require_text(data, "name", 160)
        domain = str(data.get("domain", "")).strip().lower()
        if domain not in DOMAINS:
            raise ValueError("domain must be one of the supported research domains.")
        question = require_text(data, "researchQuestion", 1000)
        description = str(data.get("description", "")).strip()[:2000]
        client_name = require_text(data, "clientName", 240) if data.get("clientName") else ""
        objectives = str(data.get("objectives", "")).strip()[:3000]
        status = str(data.get("status", "planning")).strip().lower().replace(" ", "_")
        if status not in STATUSES:
            raise ValueError("status must be planning, active, on_hold, or completed.")
        slug = slugify(name)
        project_id = str(uuid.uuid4())
        self.client.query(
            "MERGE (p:Project {slug:$slug}) "
            "ON CREATE SET p.id=$id, p.name=$name, p.title=$name, "
            "p.description=$description, p.clientName=$clientName, "
            "p.researchQuestion=$question, p.keyQuestion=$question, "
            "p.objectives=$objectives, p.status=$status, "
            "p.createdAt=$now, p.updatedAt=$now "
            "ON MATCH SET p.updatedAt=$now "
            "WITH p MATCH (d:Domain {name:$domain}) "
            "MERGE (p)-[:BELONGS_TO]->(d) "
            "MERGE (t:Topic {name:$name}) "
            "MERGE (p)-[:IS_ABOUT]->(t) "
            "FOREACH (_ IN CASE WHEN $clientName='' THEN [] ELSE [1] END | "
            "MERGE (c:Client {name:$clientName}) "
            "MERGE (p)-[:FOR_CLIENT]->(c)) "
            "RETURN p.id AS id, p.slug AS slug",
            {"slug": slug, "id": project_id, "name": name,
             "description": description, "clientName": client_name,
             "question": question, "objectives": objectives, "status": status,
             "domain": domain, "now": date.today().isoformat()},
        )
        created = self.client.query(
            "MATCH (p:Project {slug:$slug}) RETURN p.id AS id, p.slug AS slug",
            {"slug": slug},
        )
        return created[0] if created else {"id": project_id, "slug": slug}

    def update_project(self, slug, data):
        name = require_text(data, "name", 160)
        domain = str(data.get("domain", "")).strip().lower()
        if domain not in DOMAINS:
            raise ValueError("domain must be one of the supported research domains.")
        question = require_text(data, "researchQuestion", 1000)
        status = str(data.get("status", "planning")).strip().lower().replace(" ", "_")
        if status not in STATUSES:
            raise ValueError("status must be planning, active, on_hold, or completed.")
        client_name = str(data.get("clientName", "")).strip()[:240]
        self.client.query(
            "MATCH (p:Project {slug:$slug}) "
            "SET p.name=$name, p.title=$name, p.description=$description, "
            "p.clientName=$clientName, p.researchQuestion=$question, "
            "p.keyQuestion=$question, p.objectives=$objectives, "
            "p.status=$status, p.updatedAt=$now "
            "WITH p MATCH (d:Domain {name:$domain}) "
            "MERGE (p)-[:BELONGS_TO]->(d) "
            "FOREACH (_ IN CASE WHEN $clientName='' THEN [] ELSE [1] END | "
            "MERGE (c:Client {name:$clientName}) "
            "MERGE (p)-[:FOR_CLIENT]->(c))",
            {"slug": slug, "name": name,
             "description": str(data.get("description", "")).strip()[:2000],
             "clientName": client_name, "question": question,
             "objectives": str(data.get("objectives", "")).strip()[:3000],
             "status": status, "domain": domain,
             "now": date.today().isoformat()},
        )
        return self.get_project(slug)

    def get_project(self, slug):
        rows = self.client.query(
            "MATCH (p:Project {slug:$slug})-[:BELONGS_TO]->(d:Domain) "
            "OPTIONAL MATCH (p)<-[:CONCERNS]-(f:Finding) "
            "OPTIONAL MATCH (p)<-[:ABOUT]-(s:Source) "
            "RETURN p.slug AS slug, p.id AS id, p.name AS name, p.title AS title, "
            "p.description AS description, p.clientName AS clientName, "
            "p.objectives AS objectives, p.status AS status, "
            "p.researchQuestion AS researchQuestion, d.name AS domain, "
            "p.createdAt AS createdAt, p.updatedAt AS updatedAt, "
            "collect(DISTINCT {id:f.id,title:f.title,text:f.text,statement:f.statement,"
            "source:f.source,sourceUrl:f.sourceUrl,sourceTitle:f.sourceTitle,status:f.status,confidence:f.confidence}) AS findings, "
            "collect(DISTINCT {id:s.id,title:s.title,url:s.url,kind:s.kind,"
            "author:s.author,publisher:s.publisher,publicationDate:s.publicationDate,"
            "ingestionStatus:coalesce(s.ingestionStatus,'pending'),"
            "createdAt:s.createdAt}) AS sources",
            {"slug": slug},
        )
        if not rows:
            raise KeyError("Project not found.")
        project = rows[0]
        project["findings"] = [item for item in project["findings"] if item.get("id")]
        project["sources"] = [item for item in project["sources"] if item.get("id")]
        project["entities"] = self.client.query(
            "MATCH (p:Project {slug:$slug})-[:HAS_ENTITY]->(e) "
            "RETURN e.id AS id, labels(e)[0] AS type, "
            "coalesce(e.name,e.title,e.value) AS name ORDER BY name",
            {"slug": slug},
        )
        project["relationships"] = self.graph_relationships(slug)
        project["evidence"] = self.client.query(
            "MATCH (e:Evidence)<-[:SUPPORTED_BY]-(f:Finding)-[:CONCERNS]->(p:Project {slug:$slug}) "
            "RETURN e.id AS id, e.snippet AS snippet, e.sourceUrl AS sourceUrl, "
            "f.id AS findingId, f.title AS findingTitle ORDER BY e.createdAt DESC",
            {"slug": slug},
        )
        project["insights"] = self.insights(slug)
        project["activity"] = [
            {"type": "updated", "date": project.get("updatedAt")},
            {"type": "created", "date": project.get("createdAt")},
        ]
        return project

    def _upsert_source(self, slug, fields, status, now, error=""):
        self.client.query(
            "MATCH (p:Project {slug:$slug}) "
            "MERGE (s:Source {id:$id}) "
            "ON CREATE SET s.createdAt=$now "
            "SET s.title=$title, s.kind=$kind, s.author=$author, s.publisher=$publisher, "
            "s.publicationDate=$publicationDate, s.description=$description, "
            "s.ingestionStatus=$status, s.ingestionError=$error, s.updatedAt=$now "
            "FOREACH (_ IN CASE WHEN $url <> '' THEN [1] ELSE [] END | SET s.url=$url) "
            "MERGE (s)-[:ABOUT]->(p)",
            {"slug": slug, "url": fields["url"], "id": fields["id"],
             "title": fields["title"], "kind": fields["kind"],
             "author": fields.get("author", ""), "publisher": fields.get("publisher", ""),
             "publicationDate": fields.get("publicationDate", ""),
             "description": fields.get("description", ""),
             "status": status, "error": error, "now": now},
        )

    def _mark_source_status(self, slug, source_id, status, error, now):
        self.client.query(
            "MATCH (p:Project {slug:$slug})<-[:ABOUT]-(s:Source {id:$sourceId}) "
            "SET s.ingestionStatus=$status, s.ingestionError=$error, s.updatedAt=$now",
            {"slug": slug, "sourceId": source_id, "status": status,
             "error": error, "now": now},
        )

    def add_source(self, slug, data):
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
        source_key = url or f"{slug}:{title}"
        fields = {
            "id": str(uuid.uuid5(uuid.NAMESPACE_URL, source_key)),
            "title": title,
            "url": url,
            "kind": kind,
            "author": str(data.get("author", "")).strip()[:200],
            "publisher": str(data.get("publisher", "")).strip()[:200],
            "publicationDate": str(data.get("publicationDate", "")).strip()[:40],
            "description": str(data.get("description", "")).strip()[:1000],
        }
        source_id = fields["id"]
        now = date.today().isoformat()
        if not data.get("ingest") and not content:
            self._upsert_source(slug, fields, "pending", now)
            return {"id": source_id, "documentId": None, "entities": 0,
                    "evidence": 0, "status": "pending"}
        if content:
            return self._persist_ingested_source(slug, fields, content, now)
        self._upsert_source(slug, fields, "processing", now)
        request = Request(url, headers={"User-Agent": "ResearchIntelligence/1.0"})
        try:
            with urlopen(request, timeout=self.client.settings.neo4j_timeout_sec) as response:
                content = response.read(2_000_000).decode("utf-8", errors="replace").strip()
        except (HTTPError, URLError, TimeoutError, OSError) as error:
            message = ("The source could not be retrieved. Provide document text to "
                       "ingest it manually, or verify the URL and retry.")
            self._mark_source_status(slug, source_id, "failed", message, now)
            return {"id": source_id, "documentId": None, "entities": 0,
                    "evidence": 0, "status": "failed", "warning": message}
        content = clean_content(content)
        if not content:
            message = "No readable text was found at the source."
            self._mark_source_status(slug, source_id, "failed", message, now)
            return {"id": source_id, "documentId": None, "entities": 0,
                    "evidence": 0, "status": "failed", "warning": message}
        return self._persist_ingested_source(slug, fields, content, now)

    def _persist_ingested_source(self, slug, fields, content, now):
        source_id = fields["id"]
        document_id = hashlib.sha256(content.encode("utf-8")).hexdigest()
        entities = extract_entities(content)
        evidence = extract_evidence(content, fields["url"])
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
            entity["sourceUrl"] = fields["url"]
            entity["documentId"] = document_id
            entity["evidenceId"] = evidence_by_sentence.get(entity.get("sentenceIndex", 0), "")
        self.client.query(
            "MATCH (p:Project {slug:$slug}) "
            "MERGE (s:Source {id:$id}) "
            "ON CREATE SET s.createdAt=$now "
            "SET s.title=$title, s.kind=$kind, s.author=$author, s.publisher=$publisher, "
            "s.publicationDate=$publicationDate, s.description=$description, "
            "s.contentHash=$contentHash, s.ingestionStatus='ready', "
            "s.ingestionError='', s.retrievedAt=$now, s.updatedAt=$now "
            "FOREACH (_ IN CASE WHEN $url <> '' THEN [1] ELSE [] END | SET s.url=$url) "
            "MERGE (s)-[:ABOUT]->(p) "
            "MERGE (d:Document {id:$documentId}) "
            "SET d.title=$title, d.url=$url, d.content=$content, "
            "d.projectSlug=$slug, d.sourceId=$id, d.retrievedAt=$now, d.updatedAt=$now "
            "MERGE (s)-[:HAS_DOCUMENT]->(d) "
            "WITH p, d "
            "UNWIND $entities AS entity "
            "MERGE (e {id:entity.id}) "
            "SET e.name=entity.name, e.description=entity.description, "
            "e.confidence=entity.confidenceScore, e.confidenceLabel=entity.confidence, "
            "e.mentions=entity.mentions, e.sourceId=entity.sourceId, "
            "e.sourceUrl=entity.sourceUrl, e.documentId=entity.documentId, "
            "e.evidenceId=entity.evidenceId, e.projectSlug=$slug, "
            "e.sentenceIndex=entity.sentenceIndex, e.extractedAt=$now "
            "FOREACH (_ IN CASE WHEN entity.type='Organization' THEN [1] ELSE [] END | SET e:Organization) "
            "FOREACH (_ IN CASE WHEN entity.type='Person' THEN [1] ELSE [] END | SET e:Person) "
            "FOREACH (_ IN CASE WHEN entity.type='Location' THEN [1] ELSE [] END | SET e:Location) "
            "FOREACH (_ IN CASE WHEN entity.type='Event' THEN [1] ELSE [] END | SET e:Event) "
            "FOREACH (_ IN CASE WHEN entity.type='Publication' THEN [1] ELSE [] END | SET e:Publication) "
            "FOREACH (_ IN CASE WHEN entity.type='Technology' THEN [1] ELSE [] END | SET e:Technology) "
            "FOREACH (_ IN CASE WHEN entity.type='Topic' THEN [1] ELSE [] END | SET e:Topic) "
            "MERGE (p)-[:HAS_ENTITY]->(e) "
            "MERGE (d)-[:MENTIONS]->(e)",
            {"slug": slug, "url": fields["url"], "title": fields["title"],
             "kind": fields["kind"], "author": fields["author"],
             "publisher": fields["publisher"], "publicationDate": fields["publicationDate"],
             "description": fields["description"], "id": source_id, "now": now,
             "content": content, "contentHash": document_id,
             "documentId": document_id, "entities": entities},
        )
        self.client.query(
            "MATCH (p:Project {slug:$slug}), (s:Source {id:$sourceId}), "
            "(d:Document {id:$documentId}) "
            "UNWIND $evidence AS ev "
            "MERGE (e:Evidence {id:ev.id}) "
            "SET e.claim=ev.claim, e.snippet=ev.excerpt, e.confidence=ev.confidence, "
            "e.location=ev.location, e.status=ev.status, e.sourceId=s.id, "
            "e.sourceUrl=s.url, e.documentId=d.id, e.projectSlug=p.slug, e.createdAt=$now "
            "MERGE (e)-[:FROM_SOURCE]->(s) "
            "MERGE (s)-[:HAS_EVIDENCE]->(e) "
            "MERGE (d)<-[:DOCUMENTED_IN]-(e) "
            "RETURN count(e) AS count",
            {"slug": slug, "sourceId": source_id, "documentId": document_id,
             "evidence": evidence, "now": now},
        )
        self.client.query(
            "MATCH (s:Source {id:$sourceId})-[:HAS_DOCUMENT]->(d:Document "
            "{id:$documentId})-[:MENTIONS]->(n) "
            "WITH d, n "
            "MATCH (e:Evidence {documentId:d.id}) "
            "MERGE (e)-[:MENTIONS]->(n)",
            {"sourceId": source_id, "documentId": document_id},
        )
        for left, right in zip(entities, entities[1:]):
            self.client.query(
                "MATCH (a {id:$leftId}), (b {id:$rightId}) "
                "MERGE (a)-[:RELATED_TO {sourceDocument:$documentId, sourceUrl:$sourceUrl, "
                "projectSlug:$slug, extractedAt:$now}]->(b)",
                {"leftId": left["id"], "rightId": right["id"], "documentId": document_id,
                 "sourceUrl": fields["url"], "slug": slug, "now": now},
            )
        return {"id": source_id, "documentId": document_id,
                "entities": len(entities), "evidence": len(evidence), "status": "ready"}

    def sources(self, slug, term="", kind="", status=""):
        clauses = ["(s.title =~ $titlePattern OR s.url =~ $urlPattern)" if term else ""]
        if kind:
            clauses.append("s.kind = $kind")
        if status:
            clauses.append("s.ingestionStatus = $status")
        clause = " AND ".join([item for item in clauses if item])
        return self.client.query(
            "MATCH (p:Project {slug:$slug})<-[:ABOUT]-(s:Source) "
            f"{'WHERE ' + clause + ' ' if clause else ''}"
            "OPTIONAL MATCH (s)-[:HAS_DOCUMENT]->(d:Document)-[:MENTIONS]->(n) "
            "OPTIONAL MATCH (s)-[:HAS_EVIDENCE]->(e:Evidence) "
            "RETURN s.id AS id, s.title AS title, s.url AS url, s.kind AS kind, "
            "coalesce(s.author,'') AS author, coalesce(s.publisher,'') AS publisher, "
            "coalesce(s.publicationDate,'') AS publicationDate, "
            "coalesce(s.description,'') AS description, "
            "coalesce(s.ingestionStatus,'pending') AS ingestionStatus, "
            "coalesce(s.ingestionError,'') AS ingestionError, "
            "s.createdAt AS createdAt, s.updatedAt AS updatedAt, "
            "count(DISTINCT n) AS entities, count(DISTINCT e) AS evidence "
            "ORDER BY s.updatedAt DESC, s.createdAt DESC",
            {"slug": slug, "kind": kind, "status": status,
             "titlePattern": f"(?i).*{re.escape(term)}.*",
             "urlPattern": f"(?i).*{re.escape(term)}.*"},
        )

    def get_source(self, slug, source_id):
        rows = self.client.query(
            "MATCH (p:Project {slug:$slug})<-[:ABOUT]-(s:Source {id:$sourceId}) "
            "OPTIONAL MATCH (s)-[:HAS_EVIDENCE]->(e:Evidence) "
            "OPTIONAL MATCH (s)-[:HAS_DOCUMENT]->(d:Document) "
            "OPTIONAL MATCH (s)-[:HAS_DOCUMENT]->(:Document)-[:MENTIONS]->(n) "
            "RETURN s.id AS id, s.title AS title, s.url AS url, s.kind AS kind, "
            "coalesce(s.author,'') AS author, coalesce(s.publisher,'') AS publisher, "
            "coalesce(s.publicationDate,'') AS publicationDate, "
            "coalesce(s.description,'') AS description, "
            "coalesce(s.ingestionStatus,'pending') AS ingestionStatus, "
            "coalesce(s.ingestionError,'') AS ingestionError, "
            "s.retrievedAt AS retrievedAt, s.createdAt AS createdAt, s.updatedAt AS updatedAt, "
            "d.content AS content, "
            "collect(DISTINCT {id:e.id, claim:e.claim, snippet:e.snippet, "
            "confidence:e.confidence, location:e.location, status:e.status, "
            "createdAt:e.createdAt}) AS evidence, "
"collect(DISTINCT {id:n.id, type:labels(n)[0], "
             "name:coalesce(n.name,n.title), confidence:coalesce(n.confidenceLabel,'low'), "
             "description:coalesce(n.description,'')}) AS entities",
            {"slug": slug, "sourceId": source_id},
        )
        if not rows:
            raise KeyError("Source not found.")
        source = rows[0]
        source["evidence"] = [item for item in source["evidence"] if item.get("id")]
        source["entities"] = [item for item in source["entities"] if item.get("id")]
        return source

    def reingest_source(self, slug, source_id):
        rows = self.client.query(
            "MATCH (p:Project {slug:$slug})<-[:ABOUT]-(s:Source {id:$sourceId}) "
            "RETURN s.url AS url, s.title AS title, coalesce(s.kind,'article') AS kind, "
            "coalesce(s.author,'') AS author, coalesce(s.publisher,'') AS publisher, "
            "coalesce(s.publicationDate,'') AS publicationDate, "
            "coalesce(s.description,'') AS description",
            {"slug": slug, "sourceId": source_id},
        )
        if not rows:
            raise KeyError("Source not found.")
        row = rows[0]
        return self.add_source(slug, {
            "title": row["title"],
            "url": row["url"],
            "kind": row["kind"],
            "author": row["author"],
            "publisher": row["publisher"],
            "publicationDate": row["publicationDate"],
            "description": row["description"],
            "ingest": True,
        })

    def search(self, slug, term):
        term = require_text({"term": term}, "term", 200)
        pattern = f"(?i).*{re.escape(term)}.*"
        return {
            "entities": self.client.query(
                "MATCH (p:Project {slug:$slug})-[:HAS_ENTITY]->(e) "
                "WHERE coalesce(e.name,e.title,'') =~ $pattern "
                "RETURN labels(e)[0] AS type, coalesce(e.name,e.title) AS name, "
                "e.sourceId AS sourceId",
                {"slug": slug, "pattern": pattern},
            ),
            "sources": self.client.query(
                "MATCH (p:Project {slug:$slug})<-[:ABOUT]-(s:Source) "
                "WHERE s.title =~ $pattern OR s.url =~ $pattern "
                "RETURN s.id AS id, s.title AS title, s.url AS url, "
                "s.ingestionStatus AS status",
                {"slug": slug, "pattern": pattern},
            ),
            "findings": self.client.query(
                "MATCH (f:Finding)-[:CONCERNS]->(p:Project {slug:$slug}) "
                "WHERE f.title =~ $pattern OR f.text =~ $pattern "
                "RETURN f.id AS id, f.title AS title, f.text AS text",
                {"slug": slug, "pattern": pattern},
            ),
            "relationships": self.client.query(
                "MATCH (p:Project {slug:$slug})-[:HAS_ENTITY]->(a)-[r:RELATED_TO {projectSlug:$slug}]->(b) "
                "WHERE coalesce(a.name,a.title,'') =~ $pattern OR coalesce(b.name,b.title,'') =~ $pattern "
                "RETURN coalesce(a.name,a.title) AS fromName, type(r) AS relationship, "
                "coalesce(b.name,b.title) AS toName, coalesce(r.sourceUrl, r.sourceDocument) AS sourceUrl",
                {"slug": slug, "pattern": pattern},
            ),
        }

    def add_finding(self, slug, data):
        title = require_text(data, "title", 300)
        text = require_text(data, "text", 5000)
        source = str(data.get("source", "")).strip()[:2000]
        finding_id = str(uuid.uuid4())
        confidence = str(data.get("confidence", "unassessed")).strip().lower()[:40]
        self.client.query(
            "MATCH (p:Project {slug:$slug}) "
            "MERGE (f:Finding {id:$id}) SET f.title=$title,f.text=$text,f.source=$source, "
            "f.confidence=$confidence,f.status=coalesce(f.status,'draft'),"
            "f.createdAt=coalesce(f.createdAt,$now),f.updatedAt=$now "
            "MERGE (f)-[:CONCERNS]->(p) "
            "FOREACH (url IN CASE WHEN $source='' THEN [] ELSE [$source] END | "
            "MERGE (s:Source {url:url}) "
            "ON CREATE SET s.id=$sourceId,s.title=url,s.createdAt=$now "
            "MERGE (f)-[:DRAWS_ON]->(s) "
            "MERGE (e:Evidence {id:$evidenceId}) "
            "SET e.snippet=$text,e.sourceUrl=url,e.projectSlug=$slug,e.createdAt=$now "
            "MERGE (e)-[:SUPPORTS]->(f))",
            {"slug": slug, "id": finding_id, "title": title, "text": text,
             "source": source, "sourceId": str(uuid.uuid5(uuid.NAMESPACE_URL, source)) if source else "",
             "confidence": confidence, "evidenceId": str(uuid.uuid5(
                 uuid.NAMESPACE_URL, f"{slug}:{source}:{title}"
             )), "now": date.today().isoformat()},
        )
        return finding_id

    def generate_findings(self, slug):
        evidence_items = self.client.query(
            "MATCH (p:Project {slug:$slug})<-[:ABOUT]-(s:Source)-[:HAS_EVIDENCE]->(ev:Evidence) "
            "OPTIONAL MATCH (ev)-[:MENTIONS]->(entity) "
            "RETURN p.id AS projectId, s.id AS sourceId, coalesce(s.url,'') AS sourceUrl, "
            "s.title AS sourceTitle, ev.documentId AS documentId, "
            "ev.id AS evidenceId, ev.claim AS claim, ev.snippet AS snippet, "
            "ev.confidence AS confidence, "
            "collect(DISTINCT entity.id) AS entityIds",
            {"slug": slug},
        )
        generated = []
        now = date.today().isoformat()
        for item in evidence_items:
            finding_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{slug}:finding:{item['evidenceId']}"))
            title = str(item["claim"]).capitalize()
            statement = str(item["snippet"])
            entity_ids = [value for value in item.get("entityIds", []) if value]
            
            persisted = self.client.query(
                "MATCH (p:Project {slug:$slug}), (s:Source {id:$sourceId}), "
                "(e:Evidence {id:$evidenceId}) "
                "MERGE (f:Finding {id:$findingId}) "
                "ON CREATE SET f.createdAt=$now "
                "SET f.projectId=p.id, f.title=$title, f.text=$statement, "
                "f.statement=$statement, f.status=coalesce(f.status,'needs_review'), "
                "f.confidence=$confidence, f.updatedAt=$now "
                "MERGE (f)-[:CONCERNS]->(p) "
                "MERGE (s)-[:SUPPORTS]->(f) "
                "MERGE (f)-[:SUPPORTED_BY]->(e) "
                "WITH f "
                "UNWIND (CASE WHEN size($entityIds) = 0 THEN [null] ELSE $entityIds END) AS entityId "
                "OPTIONAL MATCH (entity {id:entityId}) "
                "FOREACH (_ IN CASE WHEN entity IS NOT NULL THEN [1] ELSE [] END | MERGE (f)-[:ABOUT]->(entity)) "
                "RETURN f.status AS status",
                {"slug": slug, "projectId": item["projectId"], "sourceId": item["sourceId"],
                 "findingId": finding_id, "evidenceId": item["evidenceId"], "title": title,
                 "statement": statement, "confidence": item["confidence"], "entityIds": entity_ids,
                 "now": now},
            )
            generated.append({"id": finding_id, "title": title,
                              "status": persisted[0]["status"] if persisted else "needs_review"})
        return {"generated": generated, "count": len(generated)}

    def get_finding(self, finding_id):
        rows = self.client.query(
            "MATCH (f:Finding {id:$findingId}) "
            "OPTIONAL MATCH (f)-[:CONCERNS]->(p:Project) "
            "OPTIONAL MATCH (f)-[:SUPPORTED_BY]->(e:Evidence)-[:FROM_SOURCE]->(s:Source) "
            "OPTIONAL MATCH (f)-[:ABOUT]->(entity) "
            "RETURN f.id AS id, f.projectId AS projectId, f.title AS title, "
            "coalesce(f.statement,f.text) AS statement, f.text AS text, "
            "f.status AS status, f.confidence AS confidence, f.createdAt AS createdAt, "
            "p.slug AS projectSlug, collect(DISTINCT {id:e.id,snippet:e.snippet,sourceId:s.id,sourceUrl:s.url}) AS evidence, "
            "collect(DISTINCT {id:entity.id,type:labels(entity)[0],name:coalesce(entity.name,entity.title)}) AS entities",
            {"findingId": finding_id},
        )
        if not rows:
            raise KeyError("Finding not found.")
        result = rows[0]
        result["evidence"] = [item for item in result["evidence"] if item.get("id")]
        result["entities"] = [item for item in result["entities"] if item.get("id")]
        return result

    def update_finding(self, finding_id, data):
        status = str(data.get("status", "")).strip().lower()
        allowed = {"draft", "needs_review", "verified", "rejected"}
        if status not in allowed:
            raise ValueError("status must be draft, needs_review, verified, or rejected.")
        finding = self.get_finding(finding_id)
        transitions = {
            "draft": {"draft", "needs_review"},
            "needs_review": {"needs_review", "verified", "rejected"},
            "verified": {"verified"},
            "rejected": {"rejected", "needs_review"},
        }
        if status not in transitions.get(finding.get("status"), set()):
            raise ValueError("Unsupported finding status transition.")
        self.client.query(
            "MATCH (f:Finding {id:$findingId}) SET f.status=$status, f.updatedAt=$now",
            {"findingId": finding_id, "status": status, "now": date.today().isoformat()},
        )
        return self.get_finding(finding_id)

    def findings(self, slug):
        return self.client.query(
            "MATCH (f:Finding)-[:CONCERNS]->(p:Project {slug:$slug}) "
            "OPTIONAL MATCH (f)-[:SUPPORTED_BY]->(e:Evidence) "
            "OPTIONAL MATCH (f)-[:DRAWS_ON]->(s:Source) "
            "RETURN f.id AS id, f.title AS title, f.text AS text, "
            "f.confidence AS confidence, f.createdAt AS createdAt, "
            "collect(DISTINCT s.url) AS sources, "
            "collect(DISTINCT {id:e.id,snippet:e.snippet,sourceUrl:e.sourceUrl}) AS evidence "
            "ORDER BY f.createdAt DESC",
            {"slug": slug},
        )

    def entities(self, slug, entity_type=""):
        params = {"slug": slug, "entityType": entity_type.strip()}
        where = "WHERE labels(e)[0] = $entityType " if entity_type.strip() else " "
        return self.client.query(
            "MATCH (p:Project {slug:$slug})-[:HAS_ENTITY]->(e) "
            + where
            + "OPTIONAL MATCH (s:Source {id:e.sourceId}) "
            "OPTIONAL MATCH (ev:Evidence {id:e.evidenceId}) "
            "RETURN e.id AS id, coalesce(e.name,e.title) AS name, labels(e)[0] AS type, "
            "coalesce(toFloat(e.confidence), 0.0) AS confidence, "
            "coalesce(e.confidenceLabel, e.confidence, 'low') AS confidenceLabel, "
            "coalesce(e.description,'') AS description, "
            "coalesce(e.sourceId,'') AS sourceId, "
            "coalesce(s.title, s.url, '') AS sourceTitle, "
            "coalesce(s.url, '') AS sourceUrl, "
            "coalesce(e.evidenceId,'') AS evidenceId, "
            "coalesce(ev.snippet,'') AS evidenceSnippet, "
            "coalesce(e.demo, false) AS demo, "
            "coalesce(e.mentions, 0) AS mentions "
            "ORDER BY type, name",
            params,
        )

    def insights(self, slug):
        rows = self.client.query(
            "MATCH (p:Project {slug:$slug})-[:HAS_ENTITY]->(e) "
            "RETURN labels(e)[0] AS type, count(e) AS count ORDER BY count DESC",
            {"slug": slug},
        )
        return [{"title": "Extracted entities", "detail": f"{row['count']} {row['type']} entities"} for row in rows]

    def graph(self, slug):
        return self.client.query(
            "MATCH (p:Project {slug:$slug})-[r]-(n) "
            "RETURN labels(p)[0] AS fromType, coalesce(p.name,p.title) AS fromName, "
            "type(r) AS relationship, labels(n)[0] AS toType, "
            "coalesce(n.name,n.title,n.url,n.id) AS toName ORDER BY relationship,toName",
            {"slug": slug},
        )

    def project_report(self, slug):
        project = self.get_project(slug)
        sources = project.get("sources") or []
        findings = project.get("findings") or []
        entities = project.get("entities") or []
        relationships = project.get("relationships") or []
        verified = sum(1 for item in findings if str(item.get("status") or "").lower() == "verified")
        needs_review = sum(1 for item in findings if str(item.get("status") or "").lower() == "needs_review")
        summary_lines = [
            f"Research question: {project.get('researchQuestion') or 'Not specified.'}",
            f"Status: {project.get('status') or 'planning'}",
            f"Domain: {project.get('domain') or 'other'}",
            (
                "Scope: "
                f"{len(sources)} sources, {len(findings)} findings, {len(entities)} entities, "
                f"{len(relationships)} relationships."
            ),
        ]
        return {
            "projectSlug": slug,
            "projectName": project.get("name") or project.get("title") or slug,
            "summary": "\n".join(summary_lines),
            "generatedAt": date.today().isoformat(),
            "metrics": {
                "sources": len(sources),
                "findings": len(findings),
                "entities": len(entities),
                "relationships": len(relationships),
                "verified": verified,
                "needsReview": needs_review,
            },
            "sources": [
                {
                    "id": source.get("id"),
                    "title": source.get("title"),
                    "url": source.get("url"),
                    "kind": source.get("kind"),
                    "status": source.get("ingestionStatus"),
                }
                for source in sources
            ],
            "findings": [
                {
                    "id": finding.get("id"),
                    "title": finding.get("title"),
                    "status": finding.get("status"),
                    "confidence": finding.get("confidence"),
                    "statement": finding.get("statement") or finding.get("text") or "",
                    "sourceUrl": (finding.get("source") or ""),
                }
                for finding in findings
            ],
            "entities": [
                {"id": entity.get("id"), "name": entity.get("name"), "type": entity.get("type")}
                for entity in entities
            ],
            "relationships": [
                {
                    "fromName": row.get("fromName"),
                    "relationship": row.get("relationship"),
                    "toName": row.get("toName"),
                    "sourceUrl": row.get("sourceUrl"),
                }
                for row in relationships
            ],
        }

    # --- Knowledge graph integration ---
    @property
    def graph_repository(self):
        if not hasattr(self, "_graph_repository"):
            self._graph_repository = Neo4jGraphRepository(self)
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

    def _entity_seed_id(self, name, entity_type):
        key = name.lower().strip()
        return hashlib.sha256(f"{entity_type}:{key}".encode("utf-8")).hexdigest()[:32]

    def seed_demo_data(self, slug=PUBLIC_AI_SLUG):
        """Upsert clearly-labeled demo entities + relationships into Neo4j.

        Idempotent. Only touches the demo project. Every seeded node is flagged
        demo:true and every seeded relationship carries demo evidence so it is
        never presented as verified research.
        """
        now = date.today().isoformat()
        findings = self.findings(slug)
        finding_id = findings[0]["id"] if findings else ""
        source_rows = self.client.query(
            "MATCH (p:Project {slug:$slug})<-[:ABOUT]-(s:Source) "
            "RETURN s.id AS id, s.url AS url, s.title AS title LIMIT 1",
            {"slug": slug},
        )
        source_id = source_rows[0]["id"] if source_rows else ""
        source_url = source_rows[0]["url"] if source_rows else ""
        for entity in SEED_ENTITIES:
            entity_type = entity["type"]
            entity_id = self._entity_seed_id(entity["name"], entity_type)
            label = entity_type
            self.client.query(
                "MATCH (p:Project {slug:$slug}) "
                "MERGE (e {id:$id}) "
                "SET e.name=$name, e.description=$description, "
                "e.confidence=0.5, e.confidenceLabel='demo', e.demo=true, "
                "e.projectSlug=$slug, e.sourceId=$sourceId, e.sourceUrl=$sourceUrl, "
                "e.mentions=1, e.extractedAt=$now "
                f"SET e:{label} "
                "MERGE (p)-[:HAS_ENTITY]->(e) "
                "WITH p, e "
                "OPTIONAL MATCH (s:Source {id:$sourceId}) WHERE $sourceId <> '' "
                "FOREACH (_ IN CASE WHEN s IS NOT NULL THEN [1] ELSE [] END | MERGE (s)-[:MENTIONS]->(e)) "
                "WITH p, e "
                "OPTIONAL MATCH (f:Finding {id:$findingId}) WHERE $findingId <> '' "
                "FOREACH (_ IN CASE WHEN f IS NOT NULL THEN [1] ELSE [] END | MERGE (f)-[:ABOUT]->(e)) "
                "RETURN count(e)",
                {"slug": slug, "id": entity_id, "name": entity["name"],
                 "description": entity["description"], "label": label, "now": now,
                 "sourceId": source_id, "sourceUrl": source_url, "findingId": finding_id},
            )
        for rel in SEED_RELATIONSHIPS:
            from_type = next((e["type"] for e in SEED_ENTITIES
                              if e["name"].lower() == rel["fromName"].lower()), "Topic")
            to_type = next((e["type"] for e in SEED_ENTITIES
                            if e["name"].lower() == rel["toName"].lower()), "Topic")
            from_id = self._entity_seed_id(rel["fromName"], from_type)
            to_id = self._entity_seed_id(rel["toName"], to_type)
            rel_id = f"seed:{from_id}:{rel['relationship']}:{to_id}"
            self.client.query(
                "MATCH (a {id:$fromId}), (b {id:$toId}) "
                f"MERGE (a)-[r:{rel['relationship']} {{id:$relId}}]->(b) "
                "SET r.demo=true, r.evidence=$evidence, r.projectSlug=$slug, "
                "r.confidence=0.5, r.sourceUrl=$sourceUrl, r.extractedAt=$now",
                {"fromId": from_id, "toId": to_id, "relId": rel_id,
                 "evidence": rel["evidence"], "slug": slug,
                 "sourceUrl": source_url, "now": now},
            )
        return {
            "entities": len(SEED_ENTITIES),
            "relationships": len(SEED_RELATIONSHIPS),
            "demo": True,
        }

    def purge_meaningless_entities(self, slug=None):
        """Remove meaningless/junk entity nodes (months, days, boilerplate)."""
        rows = self.client.query(
            "MATCH (p:Project)-[:HAS_ENTITY]->(e) "
            "RETURN p.slug AS slug, e.id AS id, e.name AS name, "
            "labels(e)[0] AS type"
        )
        removed = 0
        for row in rows:
            if slug is not None and row["slug"] != slug:
                continue
            if is_meaningless_entity(row["name"], row["type"] or "Topic"):
                try:
                    self.client.query(
                        "MATCH (n {id:$id}) DETACH DELETE n RETURN count(n) AS n",
                        {"id": row["id"]},
                    )
                    removed += 1
                except Exception:
                    pass
        return removed
def initialize_schema():
    """Initialize database constraints if needed."""
    pass