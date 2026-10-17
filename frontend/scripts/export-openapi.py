"""Export schema without opening a database connection; run from frontend/."""
import json
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root / "backend"))
from strava_lens.app import app  # noqa: E402

Path("openapi.json").write_text(json.dumps(app.openapi(), indent=2) + "\n")
