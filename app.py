from backend.config import Settings, load_env

load_env()

from backend.api import create_server
from backend.neo4j_client import Neo4jClient, initialize_schema
from backend.repository import ResearchRepository


settings = Settings.from_environment()
client = Neo4jClient(settings)
repository = ResearchRepository(client)


def create_project(data):
    return repository.create_project(data)


def add_finding(slug, data):
    return repository.add_finding(slug, data)


if __name__ == "__main__":
    initialize_schema(client)
    server = create_server(settings, repository)
    print(f"Research Intelligence running at http://{settings.host}:{settings.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
