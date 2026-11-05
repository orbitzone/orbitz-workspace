#!/usr/bin/python3
"""Run the screen walkthrough on a private loopback-only Broadway display."""
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time

root=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='orbitz-workspace-display-') as folder:
    env=dict(os.environ, GDK_BACKEND='broadway', BROADWAY_DISPLAY=':43',
             DISPLAY='', XDG_RUNTIME_DIR=folder)
    server=subprocess.Popen(['broadwayd','-a','127.0.0.1',':43'],env=env,
                            stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
    try:
        for _ in range(50):
            if server.poll() is not None:raise RuntimeError(server.stderr.read().decode())
            try:
                with socket.create_connection(('127.0.0.1',8123),timeout=.1):break
            except OSError:time.sleep(.05)
        result=subprocess.run(['dbus-run-session','--',sys.executable,str(root/'tools/qa-workspace.py'),
                               '--output',str(root/'docs/qa/2026-11-03'),*sys.argv[1:]],
                              env=env,timeout=55)
    finally:
        server.terminate();server.wait(timeout=5)
    sys.exit(result.returncode)
