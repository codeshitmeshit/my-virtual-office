#!/usr/bin/env python3
"""Prepare isolated Meeting-domain startup fixtures for start.sh acceptance."""

import argparse
import json
from pathlib import Path


def write(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")


def legacy(status: Path) -> None:
    write(status / "executable-meetings.json", {
        "meetings": {
            "phase8-existing": {
                "id": "phase8-existing", "topic": "Release rehearsal", "stage": "active_discussion",
                "participants": ["release-a", "release-b"], "moderator": "release-a", "version": 1,
            }
        },
        "events": {"phase8-existing": []},
        "occupancy": {"release-a": "phase8-existing", "release-b": "phase8-existing"},
        "idempotency": {"lifecycle:phase8-existing": {"meetingId": "phase8-existing"}},
    })
    write(status / "meeting-requests.json", {
        "requests": {
            "phase8-request": {
                "id": "phase8-request", "status": "confirmed",
                "source": {"projectId": "phase8-project", "taskId": "phase8-task"},
                "conversion": {"meetingId": "phase8-existing"},
            }
        },
        "idempotency": {"request:phase8-request": {"requestId": "phase8-request"}},
    })


def invalid(status: Path) -> None:
    write(status / "meeting-domain.json", {
        "schemaVersion": 99, "meetings": {}, "events": {}, "occupancy": {}, "requests": {},
        "idempotency": {}, "metadata": {},
    })


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("legacy", "invalid"))
    parser.add_argument("status_dir", type=Path)
    args = parser.parse_args()
    args.status_dir.mkdir(parents=True, exist_ok=True)
    {"legacy": legacy, "invalid": invalid}[args.mode](args.status_dir)


if __name__ == "__main__":
    main()
