#!/usr/bin/env python3
"""Serve this folder on localhost and open Temporal Stipple in your browser.

Opening index.html straight from disk works for the image and video inputs, but
most browsers refuse camera access to a file:// page. Serving it on localhost
gives the page a real origin, and the camera works.

Usage:  python3 start.py        (or double-click start.command / start-windows.bat)
"""
import http.server
import os
import socketserver
import sys
import threading
import webbrowser

os.chdir(os.path.dirname(os.path.abspath(__file__)))

if not os.path.exists("index.html"):
    sys.exit("index.html is not next to this script — keep them in the same folder.")


class Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass  # keep the console quiet; the sketch is the output, not the access log


def main():
    # port 0 asks the OS for a free port, so a second copy never collides
    with socketserver.TCPServer(("127.0.0.1", 0), Handler) as httpd:
        url = "http://localhost:%d/index.html" % httpd.server_address[1]
        print("Temporal Stipple is running at:\n\n    %s\n" % url)
        print("Leave this window open while you use it. Ctrl+C to stop.")
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nStopped.")


if __name__ == "__main__":
    main()
