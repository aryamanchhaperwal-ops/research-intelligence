"""Canonical research domain model for Research Intelligence.

This module is the single source of truth that maps the product's research
concepts to graph vocabulary. The Neo4j store (backend/repository.py) persists
these concepts as nodes and relationships using the labels and types declared
here; the demo store (backend/memory_store.py) uses the same vocabulary so a
store can be swapped in later without changing the API or the browser.

Concepts map to Neo4j as:

  Project            -> (:Project)
  ResearchQuestion   -> (:ResearchQuestion) node owned by a project
  Source             -> (:Source) connected to its project
  Document           -> (:Document) ingested text of a source
  Finding            -> (:Finding) synthesis linked to evidence and sources
  Entity             -> one of :Person :Organization :Location :Event
                            :Company :Technology :Policy :Market :Metric
  Topic              -> (:Topic) subject tag for a project
  Relationship       -> typed graph edge between the above nodes

from dataclasses import dataclass
from typing import Any, Dict, List, Protocol, runtime_checkable


DOMAIN_LABELS = {
    "Project",
    "ResearchQuestion",
    "Domain",
    "Topic",
    "Source",
    "Document",
    "Finding",
    "Evidence",
    "Note",
    "Output",
    "Client",
}

ENTITY_LABELS = {
    "Person",
    "Organization",
    "Location",
    "Event",
    "Company",
    "Technology",
    "Policy",
    "Market",
    "Metric",
    "Community",
    "TimePeriod",
    "Theme",
    "CulturalPractice",
}

# Canonical entity type mapping: product research types -> Neo4j labels
ENTITY_TYPE_MAP = {
    "Person": "person",
    "Organization": "organization",
    "Location": "location",
    "Event": "event",
    "Company": "organization",
    "Technology": "technology",
    "Policy": "policy",
    "Market": "market",
    "Metric": "metric",
}

# Research entity classification: map a normalized name to one of the canonical types.
RESEARCH_ENTITY_TYPES = ["Person", "Organization", "Location", "Event", "Company", "Technology", "Policy", "Market", "Metric"]


RELATIONSHIP_TYPES = {
    "BELONGS_TO": ("Project", "Domain"),
    "IS_ABOUT": ("Project", "Topic"),
    "ASKED_IN": ("ResearchQuestion", "Project"),
    "FOR_CLIENT": ("Project", "Client"),
    "CONCERNS": ("Finding", "Project"),
    "ABOUT": ("Source", "Project"),
    "DRAWS_ON": ("Finding", "Source"),
    "HAS_DOCUMENT": ("Source", "Document"),
    "MENTIONS": ("Document", None),
    "HAS_ENTITY": ("Project", None),
    "RELATED_TO": (None, None),
    "SUPPORTS": ("Evidence", "Finding"),
    "SUPPORTED_BY": ("Finding", "Evidence"),
    "FROM_SOURCE": ("Evidence", "Source"),
    "DELIVERS": ("Output", "Project"),
    "ON": ("Note", "Project"),
}

RESEARCH_GRAPH_MODEL = {
    "research_project": {
        "label": "Project",
        "stores": ["name", "title", "description", "researchQuestion",
                   "keyQuestion", "objectives", "status", "domain",
                   "clientName", "createdAt", "updatedAt"],
        "relationships": [
            "BELONGS_TO Domain",
            "IS_ABOUT Topic",
            "FOR_CLIENT Client",
            "HAS_ENTITY <entity>",
            "HAS ResearchQuestion",
        ],
    },
    "research_question": {
        "label": "ResearchQuestion",
        "stores": ["text", "projectSlug", "createdAt"],
        "relationships": ["ASKED_IN Project"],
    },
    "source": {
        "label": "Source",
        "stores": ["title", "url", "kind", "contentHash", "ingestionStatus",
                   "retrievedAt"],
        "relationships": ["ABOUT Project", "HAS_DOCUMENT Document"],
    },
    "finding": {
        "label": "Finding",
        "stores": ["title", "text", "statement", "confidence", "status",
                   "createdAt", "updatedAt"],
        "relationships": [
            "CONCERNS Project",
            "DRAWS_ON Source",
            "SUPPORTED_BY Evidence",
            "ABOUT <entity>",
        ],
    },
    "entity": {
        "label": "One of the ENTITY_LABELS",
        "stores": ["name", "sourceId", "projectSlug", "extractedAt"],
        "relationships": [
            "HAS_ENTITY from Project",
            "MENTIONS from Document",
            "RELATED_TO <entity>",
        ],
    },
    "topic": {
        "label": "Topic",
        "stores": ["name", "sourceId", "projectSlug", "extractedAt"],
        "relationships": ["IS_ABOUT from Project"],
    },
    "event": {
        "label": "Event",
        "stores": ["name", "date", "sourceId", "projectSlug"],
        "relationships": ["MENTIONS from Document", "HAS_ENTITY from Project",
                          "RELATED_TO <entity>"],
    },
}


@dataclass(frozen=True)
class ResearchProject:
    name: str
    research_question: str
    domain: str
    status: str = "planning"
    description: str = ""
    objectives: str = ""
    client_name: str = ""
    slug: str = ""


@runtime_checkable
class ResearchStore(Protocol):
    storage_name: str

    def dashboard(self) -> Dict[str, Any]: ...

    def list_projects(self) -> List[Dict[str, Any]]: ...

    def create_project(self, data: Dict[str, Any]) -> Dict[str, str]: ...

    def update_project(self, slug: str, data: Dict[str, Any]) -> Dict[str, Any]: ...

    def get_project(self, slug: str) -> Dict[str, Any]: ...

    def add_source(self, slug: str, data: Dict[str, Any]) -> Dict[str, Any]: ...

    def search(self, slug: str, term: str) -> Dict[str, List[Dict[str, Any]]]: ...

    def add_finding(self, slug: str, data: Dict[str, Any]) -> str: ...

    def generate_findings(self, slug: str) -> Dict[str, Any]: ...

    def get_finding(self, finding_id: str) -> Dict[str, Any]: ...

    def update_finding(self, finding_id: str, data: Dict[str, Any]) -> Dict[str, Any]: ...

    def findings(self, slug: str) -> List[Dict[str, Any]]: ...

    def entities(self, slug: str) -> List[Dict[str, Any]]: ...

    def insights(self, slug: str) -> List[Dict[str, Any]]: ...

    def graph(self, slug: str) -> List[Dict[str, Any]]: ...