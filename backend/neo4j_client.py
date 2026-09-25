import base64
import json
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SCHEMA_PATH = ROOT / "integrations" / "neo4j" / "schema" / "schema.cypher"


class Neo4jUnavailableError(RuntimeError):
    pass


class Neo4jAuthenticationError(RuntimeError):
    pass


class Neo4jQueryError(RuntimeError):
    pass


class Neo4jClient:
    def __init__(self, settings):
        self.settings = settings

    def query(self, statement, parameters=None):
        if not self.settings.neo4j_password:
            raise Neo4jAuthenticationError(
                "Neo4j password is not configured. Set NEO4J_PASSWORD and restart the app."
            )
        payload = json.dumps({
            "statements": [{"statement": statement, "parameters": parameters or {}}]
        }).encode("utf-8")
        request = Request(
            f"{self.settings.neo4j_uri}/db/{self.settings.neo4j_database}/tx/commit",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        credentials = f"{self.settings.neo4j_user}:{self.settings.neo4j_password}"
        token = base64.b64encode(credentials.encode("utf-8")).decode("ascii")
        request.add_header("Authorization", f"Basic {token}")
        try:
            with urlopen(request, timeout=self.settings.neo4j_timeout_sec) as response:
                result = json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            if error.code in (401, 403):
                raise Neo4jAuthenticationError(
                    "Neo4j authentication failed. Configure NEO4J_PASSWORD and restart the app."
                ) from error
            raise Neo4jUnavailableError("The graph database is unavailable.") from error
        except (URLError, TimeoutError, OSError) as error:
            raise Neo4jUnavailableError("The graph database is unavailable.") from error
        if result.get("errors"):
            message = result["errors"][0].get("message", "Neo4j query failed")
            raise Neo4jQueryError(message)
        result_set = result.get("results", [{}])[0]
        columns = result_set.get("columns", [])
        return [
            dict(zip(columns, item.get("row", [])))
            for item in result_set.get("data", [])
        ]


def initialize_schema(client, schema_path=DEFAULT_SCHEMA_PATH):
    schema = Path(schema_path).read_text(encoding="utf-8")
    statements = (statement.strip() for statement in schema.split(";"))
    for statement in statements:
        if statement:
            client.query(statement)
