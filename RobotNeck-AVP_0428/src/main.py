import sys
import os

# Ensure the project root is in sys.path
root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, root_dir)

from src.core.bootstrap import configure_runtime_paths

configure_runtime_paths(root_dir)

from src.core.app import run_app

if __name__ == "__main__":
    run_app()
