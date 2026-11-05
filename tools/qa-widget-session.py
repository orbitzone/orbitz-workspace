#!/usr/bin/python3
"""Isolated Broadway and D-Bus session for desktop widget QA."""
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
root=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='orbitz-widget-display-') as folder:
    env=dict(os.environ,GDK_BACKEND='broadway',BROADWAY_DISPLAY=':47',DISPLAY='',XDG_RUNTIME_DIR=folder)
    server=subprocess.Popen(['broadwayd','-a','127.0.0.1',':47'],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
    try:
        for _ in range(50):
            if server.poll() is not None:raise RuntimeError(server.stderr.read().decode())
            try:
                with socket.create_connection(('127.0.0.1',8127),timeout=.1):break
            except OSError:time.sleep(.05)
        result=subprocess.run(['dbus-run-session','--',sys.executable,str(root/'tools/qa-desktop-widget.py')],env=env,timeout=45)
    finally:server.terminate();server.wait(timeout=5)
    sys.exit(result.returncode)
