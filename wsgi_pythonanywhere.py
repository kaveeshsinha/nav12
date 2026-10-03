"""Copy this content into the WSGI file linked from PythonAnywhere's Web tab.
Replace YOUR_PA_USERNAME in both paths first.
"""
import os
import sys
from pathlib import Path
project = '/home/YOUR_PA_USERNAME/NaV12'
sys.path.insert(0, project)
os.environ['APP_ENV'] = 'production'
os.environ['SECRET_KEY'] = Path('/home/YOUR_PA_USERNAME/.nav12-secret').read_text().strip()
os.environ['DATA_DIR'] = '/home/YOUR_PA_USERNAME/nav12-data'
from app import app as application
