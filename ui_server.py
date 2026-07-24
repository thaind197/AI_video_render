import http.server
import socketserver
import webbrowser
from pathlib import Path

PORT = 8000
UI_DIR = Path(__file__).resolve().parent / "ui"

class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(UI_DIR), **kwargs)

if __name__ == "__main__":
    print(f"\n=======================================================")
    print(f"🚀 AI VIDEO STUDIO - ANT DESIGN AUTOMATION DASHBOARD WEB")
    print(f"Server đang chạy tại: http://localhost:{PORT}")
    print(f"=======================================================\n")
    
    # Auto open browser
    webbrowser.open(f"http://localhost:{PORT}")

    with socketserver.TCPServer(("", PORT), Handler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nĐang dừng Web UI Server...")
