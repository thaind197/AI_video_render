import http.server
import socketserver
import webbrowser
import sys
import io
from pathlib import Path

# Fix Unicode encoding on Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

PORT = 8000
UI_DIR = Path(__file__).resolve().parent / "ui"

class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(UI_DIR), **kwargs)

if __name__ == "__main__":
    print(f"\n=======================================================")
    print(f">> AI VIDEO STUDIO - AUTOMATION DASHBOARD WEB")
    print(f"Server running at: http://localhost:{PORT}")
    print(f"=======================================================\n")
    
    # Auto open browser
    webbrowser.open(f"http://localhost:{PORT}")

    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", PORT), Handler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nStopping Web UI Server...")
