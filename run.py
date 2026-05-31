"""Top-level launch script for MLB Stat Card Maker."""
import sys
import os

# Ensure project root is on the path
sys.path.insert(0, os.path.dirname(__file__))

from app.main import main

if __name__ == "__main__":
    main()
