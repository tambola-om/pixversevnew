#!/usr/bin/env python3
"""Mini proxy CORS multi-fournisseurs (Ollama cloud, NVIDIA NIM, Z.ai).
Usage : python proxy_ollama.py        (port 8788 par défaut)
        python proxy_ollama.py --insecure   (désactive la vérification SSL : dépannage seulement)
        pip install truststore              (recommandé : utilise les certificats de Windows)
        python proxy_ollama.py 9000   (autre port)

Routes (le préfixe choisit le fournisseur, le reste du chemin est transmis tel quel) :
  http://localhost:8788/v1/...         -> https://ollama.com/v1/...                 (ancienne route Ollama)
  http://localhost:8788/ollama/v1/...  -> https://ollama.com/v1/...
  http://localhost:8788/nvidia/v1/...  -> https://integrate.api.nvidia.com/v1/...
  http://localhost:8788/zai/api/paas/v4/... -> https://api.z.ai/api/paas/v4/...
"""
import sys, urllib.request, urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import ssl

ARGS = [a for a in sys.argv[1:] if not a.startswith("--")]
INSECURE = "--insecure" in sys.argv
PORT = int(ARGS[0]) if ARGS else 8788


def make_ssl_context():
    """Contexte SSL : --insecure (sans vérification), sinon magasin de certificats
    du système (pip install truststore), sinon certifi, sinon Python par défaut."""
    if INSECURE:
        return ssl._create_unverified_context(), "SANS vérification des certificats (--insecure)"
    try:
        import truststore
        return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT), "certificats du système (truststore)"
    except Exception:
        pass
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where()), "certificats certifi"
    except Exception:
        pass
    return ssl.create_default_context(), "certificats Python par défaut"


SSL_CTX, SSL_MODE = make_ssl_context()

ROUTES = {
    "ollama": "https://ollama.com",
    "nvidia": "https://integrate.api.nvidia.com",
    "zai": "https://api.z.ai",
}
LEGACY_TARGET = ROUTES["ollama"]  # /v1/... sans préfixe -> Ollama


def resolve(path):
    """Retourne l'URL cible complète pour un chemin reçu, ou None."""
    parts = path.split("/", 2)  # ['', 'nvidia', 'v1/chat/completions']
    if len(parts) >= 2 and parts[1] in ROUTES:
        rest = "/" + parts[2] if len(parts) > 2 else "/"
        return ROUTES[parts[1]] + rest
    if path.startswith("/v1"):
        return LEGACY_TARGET + path
    return None


class Handler(BaseHTTPRequestHandler):
    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")

    def _reply(self, status, data, ctype="application/json"):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self._cors()
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def _forward(self, method):
        url = resolve(self.path)
        if not url:
            self._reply(404, b'{"error":"route inconnue : utilisez /ollama, /nvidia ou /zai"}')
            return
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else None
        headers = {
            "Content-Type": self.headers.get("Content-Type", "application/json"),
            "Accept": "application/json",
            "User-Agent": "realisateur-ia-proxy/1.0",
        }
        if self.headers.get("Authorization"):
            headers["Authorization"] = self.headers["Authorization"]
        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=300, context=SSL_CTX) as r:
                status, data, ctype = r.status, r.read(), r.headers.get("Content-Type", "application/json")
        except urllib.error.HTTPError as e:
            status, data, ctype = e.code, e.read(), e.headers.get("Content-Type", "application/json")
        except Exception as e:
            reason = getattr(e, "reason", e)
            msg = "Proxy : impossible de joindre %s (%s / %s : %r)" % (url, type(e).__name__, type(reason).__name__, reason)
            status, data, ctype = 502, ('{"error":{"message":%s}}' % __import__("json").dumps(msg)).encode(), "application/json"
        sys.stdout.write("%s %s -> %s\n" % (method, url, status))
        if status >= 400:
            sys.stdout.write("   DETAIL : %s\n" % data[:400].decode("utf-8", "replace").replace("\n", " "))
        sys.stdout.flush()
        self._reply(status, data, ctype)

    def do_GET(self):
        if self.path in ("/", "/health"):
            self._reply(200, ("Proxy CORS OK (v3). SSL : " + SSL_MODE + ". Routes : " + ", ".join("/" + k for k in ROUTES)).encode(), "text/plain; charset=utf-8")
            return
        self._forward("GET")
    def do_POST(self): self._forward("POST")


print("Proxy CORS actif sur http://localhost:%d" % PORT)
print("  SSL : " + SSL_MODE)
for name, target in ROUTES.items():
    print("  /%s/...  ->  %s" % (name, target))
ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
