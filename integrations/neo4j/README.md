# Neo4j Integration

Graph storage for the research-intelligence workspace. Projects, sources, findings,
evidence, entities, notes, and outputs are stored as nodes, with relationships
capturing how they connect.

## Files

| File | Purpose |
| --- | --- |
| `Neo4j.psm1` | Existing PowerShell module: config, connection, Cypher execution, schema setup |
| `config.psd1` | Non-secret defaults (local URI, user, database) |
| `.env.example` | Environment-variable template — copy to `.env` and fill in your credentials |
| `schema/schema.cypher` | Graph schema: constraints, indexes, seed domains |

## Requirements

- Neo4j 5.x running locally (or reachable via `NEO4J_URI`)
- PowerShell 5.1+
- Default user is `neo4j`; the initial password is set during Neo4j setup

## Setup

1. Copy `.env.example` to `.env` and set `NEO4J_PASSWORD`. Do not commit `.env`.
2. Load the module and connect:

```powershell
Import-Module .\integrations\neo4j\Neo4j.psm1
Test-Neo4jConnection
```

3. Apply the schema (constraints, indexes, seed domains):

```powershell
Initialize-Neo4jSchema
```

## Configuration priority

1. `NEO4J_*` process environment variables (or `.env` next to the module)
2. Defaults in `config.psd1`

Passwords are only read from `NEO4J_PASSWORD` or prompted at connect time. Nothing is hardcoded.

## Usage

```powershell
Invoke-Neo4jCypher "MERGE (p:Project { slug: 'ai-in-healthcare', title: 'AI in Healthcare', status: 'scoping' })"

Invoke-Neo4jCypher "MATCH (p:Project) RETURN p.slug AS slug, p.status AS status"

Invoke-Neo4jCypher "MATCH (m:Project { slug: 'ai-in-healthcare' })
                     MERGE (d:Domain { name: 'technology' })
                     MERGE (m)-[:BELONGS_TO]->(d)"
```

Rows are returned as objects; each property is a returned column name.

## Graph model

Nodes: `Domain`, `Project`, `Topic`, `Source`, `Document`, `Person`, `Organization`,
`Location`, `Event`, `Finding`, `Evidence`, `Note`, `Output`

Typical edges: `Project -[:BELONGS_TO]-> Domain`, `Project -[:IS_ABOUT]-> Topic`,
`Source -[:ABOUT]-> Project`, `Finding -[:DRAWS_ON]-> Source`,
`Finding -[:CONCERNS]-> Project`, `Project -[:HAS_ENTITY]-> Person|Organization|Location|Event`,
`Evidence -[:SUPPORTS]-> Finding`, `Output -[:DELIVERS]-> Project`,
`Note -[:ON]-> Project`.

## Security

- HTTP API with Basic auth over localhost by default. For non-local or sensitive deployments, set `NEO4J_URI` to an `https://` endpoint (Neo4j Bolt TLS or a reverse proxy).
- `Import-Neo4jEnvironment` only reads `.env` from the module folder; it never writes secrets to files.
- Password is kept in memory for the session only.