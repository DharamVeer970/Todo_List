"""Start Orbit — backend API and UI, one process.

    python main.py

Everything else lives in Backend/ and Frontend/; this just wires them up so
you can run the app from the project root.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "Backend"))

from app import main  # type: ignore[reportMissingImports]

if __name__ == "__main__":
    main()
