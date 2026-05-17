import argparse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class MaintenanceHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, root_path=None, **kwargs):
        self.root_path = Path(root_path)
        super().__init__(*args, directory=str(self.root_path), **kwargs)

    def do_GET(self):
        if self.path.startswith("/static/"):
            return super().do_GET()
        self.path = "/static/maintenance.html"
        return super().do_GET()

    def log_message(self, format, *args):
        return None


def main():
    parser = argparse.ArgumentParser(description="Serve the static maintenance page during app restarts.")
    parser.add_argument("--root", required=True)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=5055)
    args = parser.parse_args()

    def handler(*handler_args, **handler_kwargs):
        return MaintenanceHandler(*handler_args, root_path=args.root, **handler_kwargs)

    server = ThreadingHTTPServer((args.host, args.port), handler)
    server.serve_forever()


if __name__ == "__main__":
    main()
