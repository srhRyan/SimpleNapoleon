"""
WSGI entry point for PythonAnywhere deployment.

PythonAnywhere setup:
1. Upload project to /home/<username>/SimpleNapoleon/
2. Create virtualenv: mkvirtualenv napoleon --python=python3.10
3. pip install -r requirements.txt
4. Web tab -> Add new web app -> Manual config -> Python 3.10
5. Source code: /home/<username>/SimpleNapoleon
6. Virtualenv: /home/<username>/.virtualenvs/napoleon
7. WSGI config file -> paste contents below
8. Static files: URL=/static, Directory=/home/<username>/SimpleNapoleon/static
"""

import sys
import os

# Add project to path
project_home = os.path.dirname(os.path.abspath(__file__))
if project_home not in sys.path:
    sys.path.insert(0, project_home)

from server import app, socketio

# PythonAnywhere uses WSGI, not direct socketio.run()
# Flask-SocketIO will fall back to long-polling (no WebSocket on free tier)
application = app
