#!/usr/bin/env python3
"""WSGI and local entry point for MSX ROM & DSK Server."""

import os
from app import app
from app.utils import SERVE_DIRECTORY

if __name__ == "__main__":
    os.makedirs(SERVE_DIRECTORY, exist_ok=True)
    app.run(debug=True, host="0.0.0.0", port=5001)
