import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from .config import ROOT, Settings
from .auth import auth_service
from .ai_provider import ai_service
from .neo4j_client import Neo4jAuthenticationError, Neo4jClient, Neo4jQueryError, Neo4jUnavailableError
from .repository import ResearchRepository


class ApiHandler(BaseHTTPRequestHandler):
    repository = None

    def set_cors_headers(self):
        origin = self.headers.get("Origin")
        if origin:
            self.send_header("Access-Control-Allow-Origin", origin)
        else:
            self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, PATCH, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Access-Control-Allow-Credentials", "true")

    def do_OPTIONS(self):
        self.send_response(204)
        self.set_cors_headers()
        self.end_headers()

    def send_json(self, payload, status=200):
        import datetime
        response = {
            "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
            "data": payload
        }
        body = json.dumps(response).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.set_cors_headers()
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def request_body(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
            return json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, json.JSONDecodeError) as error:
            raise ValueError("Request body must be valid JSON.") from error

    def _authenticate(self):
        # Bypass authentication for local development
        return {"sub": "local-developer"}


    def error(self, error):
        if isinstance(error, (ValueError, KeyError)):
            return self.send_json({"error": str(error)}, 400 if isinstance(error, ValueError) else 404)
        if isinstance(error, Neo4jUnavailableError):
            return self.send_json({"error": str(error)}, 503)
        if isinstance(error, Neo4jAuthenticationError):
            return self.send_json({"error": str(error)}, 503)
        if isinstance(error, Neo4jQueryError):
            return self.send_json({"error": "The graph operation could not be completed."}, 502)
        return self.send_json({"error": "An internal server error occurred."}, 500)

    def do_GET(self):
        if self.path not in ("/", "/index.html", "/styles.css", "/app.js") and not self.path.startswith("/api/auth"):
            user = self._authenticate()
            if not user:
                return self.send_json({"error": "Unauthorized"}, 401)
        
        path = [unquote(part) for part in urlparse(self.path).path.split("/") if part]
        try:
            if path == ["api", "health"]:
                storage = getattr(self.repository, "storage_name", "neo4j")
                return self.send_json({
                    "status": "ok",
                    "service": "research-intelligence",
                    "storage": storage,
                })
            if path == ["api", "dashboard"]:
                return self.send_json(self.repository.dashboard())
            if path == ["api", "projects"]:
                return self.send_json({"projects": self.repository.list_projects()})
            if len(path) == 3 and path[:2] == ["api", "projects"] and path[2] == "": 
                return self.send_json({"projects": self.repository.list_projects()})
            if len(path) == 3 and path[:2] == ["api", "projects"]:
                return self.send_json(self.repository.get_project(path[2]))
            if len(path) == 4 and path[:2] == ["api", "projects"] and path[3] == "graph":
                graph = self.repository.graph_data(path[2])
                graph["storage"] = getattr(self.repository, "storage_name", "graph")
                graph["mode"] = getattr(self.repository, "storage_name", "graph")
                return self.send_json(graph)
            if len(path) == 5 and path[:2] == ["api", "projects"] and path[3] == "graph":
                if path[4] == "nodes":
                    return self.send_json({"nodes": self.repository.graph_nodes(path[2])})
                if path[4] == "relationships":
                    return self.send_json({"relationships": self.repository.graph_relationships(path[2])})
                if path[4] == "search":
                    term = parse_qs(urlparse(self.path).query).get("q", [""])[0]
                    return self.send_json({"results": self.repository.graph_search(path[2], term)})
                return self.send_json({"error": "Not found."}, 404)
            if len(path) == 6 and path[:2] == ["api", "projects"] and path[3] == "graph" and path[4] == "nodes":
                return self.send_json(self.repository.graph_node(path[2], path[5]))
            if len(path) == 4 and path[:2] == ["api", "projects"] and path[3] == "findings":
                return self.send_json(self.repository.findings(path[2]))
            if len(path) == 4 and path[:2] == ["api", "projects"] and path[3] in {"report", "reports"}:
                return self.send_json(self.repository.project_report(path[2]))
            if len(path) == 4 and path[:2] == ["api", "projects"] and path[3] == "entities":
                query = parse_qs(urlparse(self.path).query)
                return self.send_json(self.repository.entities(
                    path[2], query.get("type", [""])[0],
                ))
            if len(path) == 4 and path[:2] == ["api", "projects"] and path[3] == "sources":
                query = parse_qs(urlparse(self.path).query)
                return self.send_json(self.repository.sources(
                    path[2],
                    query.get("q", [""])[0],
                    query.get("kind", [""])[0],
                    query.get("status", [""])[0],
                ))
            if len(path) == 5 and path[:2] == ["api", "projects"] and path[3] == "sources":
                return self.send_json(self.repository.get_source(path[2], path[4]))
            if len(path) == 4 and path[:2] == ["api", "projects"] and path[3] == "search":
                term = parse_qs(urlparse(self.path).query).get("q", [""])[0]
                return self.send_json(self.repository.search(path[2], term))
            if len(path) == 3 and path[:2] == ["api", "findings"]:
                return self.send_json(self.repository.get_finding(path[2]))
            if self.path in ("/", "/index.html"):
                return self.static_file("index.html", "text/html; charset=utf-8")
            if self.path == "/styles.css":
                return self.static_file("styles.css", "text/css; charset=utf-8")
            if self.path == "/app.js":
                return self.static_file("app.js", "text/javascript; charset=utf-8")
            return self.send_json({"error": "Not found."}, 404)
        except Exception as error:
            return self.error(error)

    def do_POST(self):
        if self.path == "/api/auth/login":
            try:
                data = self.request_body()
                username = str(data.get("username", "")).strip()
                password = str(data.get("password", "")).strip()
                token, user = auth_service.authenticate(username, password)
                if not token:
                    return self.send_json({"error": "Invalid credentials"}, 401)
                return self.send_json({"token": token, "user": {"username": user.username, "role": user.role}}, 200)
            except Exception as error:
                return self.error(error)

        if not self.path.startswith("/api/auth"):
            user = self._authenticate()
            if not user:
                return self.send_json({"error": "Unauthorized"}, 401)
        
        path = [unquote(part) for part in urlparse(self.path).path.split("/") if part]
        try:
            data = self.request_body()
            if path == ["api", "projects"]:
                return self.send_json(self.repository.create_project(data), 201)
            if len(path) == 4 and path[:2] == ["api", "projects"]:
                if path[3] == "sources":
                    return self.send_json(self.repository.add_source(path[2], data), 201)
                if path[3] == "findings":
                    return self.send_json({"id": self.repository.add_finding(path[2], data)}, 201)
            if len(path) == 5 and path[:2] == ["api", "projects"] and path[3] == "findings" and path[4] == "generate":
                return self.send_json(self.repository.generate_findings(path[2]), 201)
            if len(path) == 6 and path[:2] == ["api", "projects"] and path[3] == "sources" and path[5] == "reingest":
                return self.send_json(self.repository.reingest_source(path[2], path[4]), 201)
            if path == ["api", "ai", "research"]:
                question = str(data.get("question", "")).strip()
                if not question or len(question) > 2000:
                    raise ValueError("question is required and must be under 2000 characters.")
                action = str(data.get("action", "analyze")).strip().lower()
                
                try:
                    if action == "analyze":
                        slug = str(data.get("projectSlug", "")).strip()
                        if not slug:
                            raise ValueError("projectSlug is required for analysis.")
                            
                        import re
                        words = [w for w in re.findall(r'\b\w{4,}\b', question.lower()) if w not in {'what', 'when', 'where', 'which', 'who', 'how', 'this', 'that', 'these', 'those'}]
                        
                        context_parts = []
                        provenance = []
                        seen_prov = set()
                        
                        project = self.repository.get_project(slug)
                        
                        for f in project.get("findings", []):
                            text = str(f.get("text") or f.get("statement") or "")
                            title = str(f.get("title") or "")
                            if not words or any(w in text.lower() or w in title.lower() for w in words):
                                context_parts.append(f"Finding: {title} - {text}")
                                prov_key = f"Finding:{title}"
                                if prov_key not in seen_prov:
                                    provenance.append({
                                        "type": "Finding", 
                                        "title": title, 
                                        "text": text,
                                        "sourceTitle": str(f.get("sourceTitle") or ""),
                                        "sourceUrl": str(f.get("sourceUrl") or "")
                                    })
                                    seen_prov.add(prov_key)
                        
                        for r in project.get("relationships", []):
                            text = f"{r.get('fromName')} {r.get('toName')} {r.get('relationship')} {r.get('sourceUrl')}"
                            if not words or any(w in text.lower() for w in words):
                                context_parts.append(f"Relationship: {r.get('fromName')} -> {r.get('relationship')} -> {r.get('toName')}")
                                if r.get('sourceUrl'):
                                    prov_key = f"Source:{r.get('sourceUrl')}"
                                    if prov_key not in seen_prov:
                                        provenance.append({"type": "Source Evidence", "title": "Graph Relationship", "text": r.get('sourceUrl')})
                                        seen_prov.add(prov_key)
                                        
                        if not context_parts:
                            context_parts.append("No directly matching findings or relationships found. Project summary:")
                            context_parts.append(f"Description: {project.get('description')}")
                        
                        context = "\n".join(context_parts)
                        res = ai_service.analyze(question, context)
                        return self.send_json({
                            "status": "success", 
                            "result": res.content, 
                            "metadata": res.metadata,
                            "provenance": provenance
                        })
                    elif action == "find-sources":
                        res = ai_service.find_sources(question)
                        return self.send_json({"status": "success", "sources": res})
                    elif action == "generate-findings":
                        source_content = str(data.get("content", "")).strip()
                        res = ai_service.generate_findings(source_content, question)
                        return self.send_json({"status": "success", "findings": res})
                    else:
                        raise ValueError("Unsupported research action.")
                except Exception as error:
                    return self.send_json({"status": "error", "message": str(error)}, 500)
            return self.send_json({"error": "Not found."}, 404)
        except Exception as error:
            return self.error(error)

    def do_PUT(self):
        user = self._authenticate()
        if not user:
            return self.send_json({"error": "Unauthorized"}, 401)
            
        path = [unquote(part) for part in urlparse(self.path).path.split("/") if part]
        try:
            if len(path) == 3 and path[:2] == ["api", "projects"]:
                return self.send_json(self.repository.update_project(path[2], self.request_body()))
            return self.send_json({"error": "Not found."}, 404)
        except Exception as error:
            return self.error(error)

    def do_PATCH(self):
        user = self._authenticate()
        if not user:
            return self.send_json({"error": "Unauthorized"}, 401)
            
        path = [unquote(part) for part in urlparse(self.path).path.split("/") if part]
        try:
            if len(path) == 3 and path[:2] == ["api", "findings"]:
                return self.send_json(self.repository.update_finding(path[2], self.request_body()))
            return self.send_json({"error": "Not found."}, 404)
        except Exception as error:
            return self.error(error)

    def static_file(self, name, content_type):
        body = (ROOT / "web" / name).read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_):
        pass


def create_server(settings=None, repository=None):
    settings = settings or Settings.from_environment()
    ApiHandler.repository = repository or ResearchRepository(
        Neo4jClient(settings)
    )
    return ThreadingHTTPServer((settings.host, settings.port), ApiHandler)
