# Research Intelligence

Research Intelligence is an enterprise-oriented foundation for turning research
questions, evidence, and findings into connected, reusable intelligence.

## Current MVP

- Professional application shell with dashboard, projects, sources, findings,
  knowledge graph, AI research, and settings navigation.
- Project creation with name, domain, research question, description, status,
  client/organization, objectives, timestamps, stable IDs, and project-scoped
  graph relationships.
- Source and finding capture inside a project workspace.
- Neo4j-backed metrics, project detail, source/finding, and relationship queries.
- Graph-ready entity model for projects, topics, sources, documents, people,
  organizations, locations, events, findings, evidence, notes, and outputs.
- Provider-neutral AI research endpoint with Analyze, Find Sources, and Generate
  Findings actions ready for an API provider integration.

## Architecture

```
app.py                       Process entrypoint
backend/
  config.py                  Environment-backed application settings
  neo4j_client.py            Transactional HTTP client and safe error boundary
  repository.py              Research domain/data access layer
  api.py                     HTTP routing, validation, and static file serving
web/
  index.html                 Application shell and workspace markup
  styles.css                 Responsive product UI
  app.js                     Browser state, navigation, and API client
integrations/neo4j/
  Neo4j.psm1                 Existing PowerShell integration
  schema/schema.cypher       Constraints, indexes, domains, and graph model
tests/                       Unit tests for domain/repository behavior
```

The backend is deliberately split into configuration, integration, data access,
and transport layers so authentication, organizations, permissions, audit logs,
background jobs, ingestion, and multiple AI providers can be added without
coupling them to the browser.

## Setup

Requirements: Python 3.9+, Neo4j 5.x, and the packages in `requirements.txt`.

1. Copy `integrations/neo4j/.env.example` to `integrations/neo4j/.env`.
2. Set `NEO4J_PASSWORD` and any deployment-specific values.
3. Start the application. On startup, it loads the schema and creates any
missing constraints and indexes:

```powershell
python .\app.py
```

4. Open `http://localhost:8000`.

## Environment variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `APP_HOST` | `localhost` | HTTP bind host |
| `PORT` | `8000` | HTTP port |
| `NEO4J_URI` | `bolt://127.0.0.1:7687` | Neo4j endpoint, converted to the HTTP transaction API |
| `NEO4J_USER` | `neo4j` | Neo4j username |
| `NEO4J_PASSWORD` | empty | Secret, never returned to clients |
| `NEO4J_DATABASE` | `neo4j` | Neo4j database |
| `NEO4J_TIMEOUT_SEC` | `30` | Query timeout |

## Neo4j model

Projects connect to domains and topics. Projects contain sources, findings,
entities, and evidence. Findings draw on sources and concern projects. The
schema also reserves stable identifiers and indexes for documents, people,
organizations, locations, events, notes, and outputs. All application reads and
writes use parameterized Cypher through the existing transactional HTTP
integration; the browser never receives credentials.

## API

- `GET /api/health`
- `GET /api/dashboard`
- `GET /api/projects`
- `POST /api/projects`
- `PUT /api/projects/{slug}`
- `GET /api/projects/{slug}`
- `POST /api/projects/{slug}/sources`
- `POST /api/projects/{slug}/findings`
- `GET /api/projects/{slug}/graph`
- `GET /api/projects/{slug}/search?q=term`
- `POST /api/ai/research`

Source ingestion accepts `title`, `url`, `kind`, and optional `content`. Set
`ingest` to `true` (the web workspace does this automatically) to retrieve the
URL when content is omitted, clean the page text, store a `Document`, extract
bounded deterministic Organization/Topic entities, and connect them to the
project. Extracted graph properties include source/project provenance. Source
IDs, document hashes, entities, and relationships are merged so retrying the
same source is safe. Project search returns categorized entities, sources,
findings, and relationships.

## Validation

```powershell
python -m py_compile .\app.py .\backend\*.py .\tests\test_app.py
python -m unittest discover -s .\tests -v
```

## Enterprise roadmap

The next layers should add organization/workspace tenancy, authentication and
role-based authorization, audit events, asynchronous document ingestion,
full-text/vector retrieval, provider adapters for AI and external research
APIs, exports/reporting, observability, migrations, and cloud deployment.
