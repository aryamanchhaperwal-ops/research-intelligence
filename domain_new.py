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
"""from dataclasses import dataclass
from typing import Any, Dict, List, Protocol, runtime_checkable
