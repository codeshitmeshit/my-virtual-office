#!/usr/bin/env python3
"""Auxiliary real-filesystem benchmark for MarkdownProjectStore.revision()."""

import argparse
import json
import os
import statistics
import sys
import tempfile
import time


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(ROOT, "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from project_store import MarkdownProjectStore


SCALES = {"small": (5, 10), "medium": (50, 50), "large": (200, 100)}


def fixture(project_count, task_count):
    return {
        "projects": [{
            "id": f"project-{project_index}",
            "title": f"Project {project_index}",
            "updatedAt": "before",
            "columns": [{"id": f"backlog-{project_index}", "title": "Backlog", "order": 0}],
            "activity": [],
            "tasks": [{
                "id": f"task-{project_index}-{task_index}",
                "title": f"Task {project_index}-{task_index}",
                "columnId": f"backlog-{project_index}",
                "order": task_index,
                "updatedAt": "before",
                "attempts": [],
                "comments": [],
            } for task_index in range(task_count)],
        } for project_index in range(project_count)],
        "templates": [],
    }


def percentile95(values):
    ordered = sorted(values)
    return ordered[max(0, min(len(ordered) - 1, int(len(ordered) * 0.95) - 1))]


def measure(scale, warmups, runs):
    project_count, task_count = SCALES[scale]
    with tempfile.TemporaryDirectory(prefix=f"vo-revision-{scale}-") as status_dir:
        store = MarkdownProjectStore(status_dir)
        store.save_all(fixture(project_count, task_count))
        file_count = sum(len(files) for _, _, files in os.walk(store.projects_dir))
        for _ in range(warmups):
            store.revision()
            store.poll_external_revision()
        samples = []
        quick_samples = []
        scan_samples = []
        for _ in range(runs):
            started = time.perf_counter_ns()
            store.revision()
            samples.append((time.perf_counter_ns() - started) / 1_000_000)
            started = time.perf_counter_ns()
            store._quick_revision_signature()
            quick_samples.append((time.perf_counter_ns() - started) / 1_000_000)
            started = time.perf_counter_ns()
            store.poll_external_revision()
            scan_samples.append((time.perf_counter_ns() - started) / 1_000_000)
        return {
            "projects": project_count,
            "tasksPerProject": task_count,
            "filesScanned": file_count,
            "revisionMedianMs": round(statistics.median(samples), 3),
            "revisionP95Ms": round(percentile95(samples), 3),
            "quickWatcherMedianMs": round(statistics.median(quick_samples), 3),
            "quickWatcherP95Ms": round(percentile95(quick_samples), 3),
            "backgroundScanMedianMs": round(statistics.median(scan_samples), 3),
            "backgroundScanP95Ms": round(percentile95(scan_samples), 3),
        }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scales", default="small,medium,large")
    parser.add_argument("--warmups", type=int, default=3)
    parser.add_argument("--runs", type=int, default=20)
    parser.add_argument("--output")
    args = parser.parse_args()
    result = {
        "warmups": args.warmups,
        "runs": args.runs,
        "scales": {scale: measure(scale, args.warmups, args.runs) for scale in args.scales.split(",")},
    }
    rendered = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as output_file:
            output_file.write(rendered + "\n")
    print(rendered)


if __name__ == "__main__":
    main()
