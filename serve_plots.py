#!/usr/bin/env python3
"""
serve_plots.py
--------------
Serve a directory over HTTP so plots can be viewed in the Windows browser
without copying anything to /mnt/c.

Run it OUTSIDE the lb-run container, in its own terminal, and leave it going:

    python3 serve_plots.py ~/data 8000

Or run this line anywhere (doesn't matter if it's in the same container):

    nohup python3 ~/data/serve_plots.py ~/data 8000 > ~/serve_plots.log 2>&1 &

Then open http://localhost:8000/ in Windows. WSL2 forwards localhost to the
Windows host, so nothing else needs configuring.

Every response carries no-cache headers, which matters: without them the
browser happily shows you the plot from twenty minutes ago after you have
rerun the fit. Refresh and you get the current file.

This function was created since images didn't seem to open from my container, but if one 
doesn't face this issue, the file can be ignored entirely, and all instances of the show()
function should be removed from the plot scripts.
"""

import http.server
import os
import socketserver
import sys

DIRECTORY = os.path.abspath(os.path.expanduser(
    sys.argv[1] if len(sys.argv) > 1 else '~/data'))
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 8000


class NoCacheHandler(http.server.SimpleHTTPRequestHandler):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIRECTORY, **kwargs)

    def end_headers(self):
        self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate')
        self.send_header('Pragma', 'no-cache')
        self.send_header('Expires', '0')
        super().end_headers()

    def log_message(self, fmt, *args):
        pass          # the plotting output is noisy enough already


if not os.path.isdir(DIRECTORY):
    sys.exit('%s is not a directory' % DIRECTORY)

socketserver.TCPServer.allow_reuse_address = True

# 0.0.0.0 rather than 127.0.0.1: WSL2 sits behind its own NAT, so this is
# reachable from the Windows host but not from the wider network.
with socketserver.TCPServer(('0.0.0.0', PORT), NoCacheHandler) as httpd:
    print('serving %s' % DIRECTORY)
    print('open http://localhost:%d/ in Windows   (Ctrl-C to stop)' % PORT)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print('\nstopped')
