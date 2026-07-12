#!/usr/bin/env python3
"""Execute the fixed Phase 1 Meeting characterization nodes."""

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
manifest_path = ROOT / "openspec/changes/extract-meeting-and-collaboration-services/characterization-manifest.json"
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
command = [sys.executable, "-m", "pytest", "-q", *manifest["nodeIds"]]
completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
report = {
    "schema": 1, "nodeCount": len(manifest["nodeIds"]), "exitCode": completed.returncode,
    "command": command, "stdout": completed.stdout, "stderr": completed.stderr,
}
print(json.dumps(report, indent=2))
raise SystemExit(completed.returncode)
