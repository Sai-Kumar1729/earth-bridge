"""earth-bridge Studio: the browser UI and its local server.

This file exists so setuptools discovers web_studio as a package. Without it
`find_packages` skipped the directory entirely and the built wheel shipped no
server, no HTML and no JavaScript, so `earthbridge studio` could not work for
anyone who installed from PyPI.
"""

import os

STUDIO_DIR = os.path.dirname(os.path.abspath(__file__))
SERVER_PATH = os.path.join(STUDIO_DIR, "server.py")

__all__ = ["STUDIO_DIR", "SERVER_PATH"]
