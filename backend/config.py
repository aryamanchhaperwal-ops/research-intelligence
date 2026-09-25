from dotenv import load_dotenv
import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse, urlunparse


ROOT = Path(__file__).resolve().parent.parent
ENV_FILES = (ROOT / ".env", ROOT / "integrations" / "neo4j" / ".env")


def load_env():
    for env_file in ENV_FILES:
        load_dotenv(dotenv_path=env_file, override=False)


def http_uri(value):
    parsed = urlparse(value)
    if parsed.scheme not in ("neo4j", "bolt", "neo4j+s", "bolt+s"):
        return value.rstrip("/")
    port = parsed.port
    if port in (None, 7687):
        port = 7474
    scheme = "https" if parsed.scheme.endswith("+s") else "http"
    return urlunparse((scheme, parsed.hostname + (f":{port}" if port else ""), "", "", "", "")).rstrip("/")


@dataclass(frozen=True)
class Settings:
    host: str
    port: int
    neo4j_uri: str
    neo4j_user: str
    neo4j_password: str
    neo4j_database: str
    neo4j_timeout_sec: int

    @classmethod
    def from_environment(cls):
        load_env()
        return cls(
            host=os.getenv("APP_HOST", "localhost"),
            port=int(os.getenv("PORT", "8000")),
            neo4j_uri=http_uri(os.getenv("NEO4J_URI", "bolt://127.0.0.1:7687")),
            neo4j_user=os.getenv("NEO4J_USER", "neo4j"),
            neo4j_password=os.getenv("NEO4J_PASSWORD", ""),
            neo4j_database=os.getenv("NEO4J_DATABASE", "neo4j"),
            neo4j_timeout_sec=int(os.getenv("NEO4J_TIMEOUT_SEC", "30")),
        )
