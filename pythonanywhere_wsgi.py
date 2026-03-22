"""
PythonAnywhere WSGI Configuration.

Copy this into: /var/www/<username>_pythonanywhere_com_wsgi.py
Replace <username> with your PythonAnywhere username.
"""

import sys
import os

# ---- CHANGE THIS ----
username = 'CHANGE_ME'
# ----------------------

project_path = f'/home/{username}/SimpleNapoleon'
if project_path not in sys.path:
    sys.path.insert(0, project_path)
os.chdir(project_path)

from server import app, socketio

# Flask-SocketIO patches app.wsgi_app automatically
application = app
