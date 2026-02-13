#!/usr/bin/env python3
"""
Compare app-graph.json between base and head commits and produce a
Markdown diff summary suitable for posting as a PR comment.

Usage (CI):
    python scripts/graph_diff.py

Environment variables:
    GRAPH_FILES  — newline-separated list of .radius/app-graph.json paths
                   that changed in this PR (set by the workflow).
    BASE_SHA     — base commit SHA (PR target branch).
    HEAD_SHA     — head commit SHA (PR source branch).
    DIFF_OUTPUT  — path to write the Markdown output (default: stdout).
"""

import json
import os
import subprocess
import sys


# ── helpers ──────────────────────────────────────────────────────────

def git_show(sha: str, path: str) -> str | None:
    """Return file contents at a given commit, or None if missing."""
    try:
        result = subprocess.run(
            ["git", "show", f"{sha}:{path}"],
            capture_output=True, text=True, check=True,
        )
        return result.stdout
    except subprocess.CalledProcessError:
        return None


def parse_graph(raw: str | None) -> dict:
    """Parse app-graph JSON into a normalised dict."""
    if not raw:
        return {"resources": {}, "connections": []}
    data = json.loads(raw)
    resources = {}
    for r in data.get("resources", []):
        resources[r.get("id", r.get("name", ""))] = r
    connections = []
    for c in data.get("connections", []):
        if c.get("type") != "dependsOn":
            connections.append((c.get("sourceId", ""), c.get("targetId", "")))
    return {"resources": resources, "connections": connections}


def resource_label(res: dict) -> str:
    """Human-readable one-liner for a resource."""
    name = res.get("name", "?")
    rtype = res.get("type", "").rsplit("/", 1)[-1]
    loc = res.get("sourceLocation", {})
    file = loc.get("file", "")
    line = loc.get("line", "")
    parts = [f"**{name}**", f"`{rtype}`"]
    if file:
        parts.append(f"{file}:{line}" if line else file)
    return " — ".join(parts)


def resolve_name(res_id: str, resources: dict) -> str:
    """Get a short display name from a resource id or target string."""
    if res_id in resources:
        return resources[res_id].get("name", res_id)
    # ARM expression like [reference('database').id]
    import re
    arm_match = re.match(r"\[reference\('(\w+)'\)", res_id)
    if arm_match:
        sym = arm_match.group(1)
        for r in resources.values():
            if r.get("name") == sym:
                return sym
        return sym
    # URL like http://backend:3000
    url_match = re.match(r"https?://([^:/]+)", res_id)
    if url_match:
        hostname = url_match.group(1)
        for r in resources.values():
            if r.get("name") == hostname:
                return hostname
        return hostname
    # Last path segment
    return res_id.rstrip("/").rsplit("/", 1)[-1]


# ── diff logic ───────────────────────────────────────────────────────

def diff_graphs(base: dict, head: dict) -> dict:
    """Compute added / removed / modified resources and connections."""
    base_ids = set(base["resources"])
    head_ids = set(head["resources"])

    added = head_ids - base_ids
    removed = base_ids - head_ids
    common = base_ids & head_ids

    modified = set()
    for rid in common:
        if json.dumps(base["resources"][rid], sort_keys=True) != json.dumps(
            head["resources"][rid], sort_keys=True
        ):
            modified.add(rid)

    base_conns = set(base["connections"])
    head_conns = set(head["connections"])
    added_conns = head_conns - base_conns
    removed_conns = base_conns - head_conns

    return {
        "added": added,
        "removed": removed,
        "modified": modified,
        "unchanged": common - modified,
        "added_conns": added_conns,
        "removed_conns": removed_conns,
    }


# ── markdown rendering ──────────────────────────────────────────────

def render_diff_section(app_path: str, base_graph: dict, head_graph: dict, diff: dict) -> str:
    """Render a Markdown section for one application's diff."""
    lines: list[str] = []
    app_label = app_path.replace("/.radius/app-graph.json", "") or "(root)"
    lines.append(f"### 📦 `{app_label}`\n")

    has_changes = diff["added"] or diff["removed"] or diff["modified"] or diff["added_conns"] or diff["removed_conns"]

    if not has_changes:
        lines.append("> No resource or connection changes.\n")
        return "\n".join(lines)

    # Resources table
    if diff["added"] or diff["removed"] or diff["modified"]:
        lines.append("#### Resources\n")
        lines.append("| Status | Resource |")
        lines.append("|--------|----------|")
        for rid in sorted(diff["added"]):
            lines.append(f"| 🟢 Added | {resource_label(head_graph['resources'][rid])} |")
        for rid in sorted(diff["removed"]):
            lines.append(f"| 🔴 Removed | {resource_label(base_graph['resources'][rid])} |")
        for rid in sorted(diff["modified"]):
            lines.append(f"| 🟡 Modified | {resource_label(head_graph['resources'][rid])} |")
        lines.append("")

    # Connections
    all_res = {**base_graph["resources"], **head_graph["resources"]}
    if diff["added_conns"] or diff["removed_conns"]:
        lines.append("#### Connections\n")
        lines.append("| Status | Connection |")
        lines.append("|--------|------------|")
        for src, tgt in sorted(diff["added_conns"]):
            lines.append(f"| 🟢 Added | {resolve_name(src, all_res)} → {resolve_name(tgt, all_res)} |")
        for src, tgt in sorted(diff["removed_conns"]):
            lines.append(f"| 🔴 Removed | {resolve_name(src, all_res)} → {resolve_name(tgt, all_res)} |")
        lines.append("")

    # Summary counts
    summary = []
    if diff["added"]:
        summary.append(f"+{len(diff['added'])} added")
    if diff["removed"]:
        summary.append(f"-{len(diff['removed'])} removed")
    if diff["modified"]:
        summary.append(f"~{len(diff['modified'])} modified")
    if diff["unchanged"]:
        summary.append(f"{len(diff['unchanged'])} unchanged")
    lines.append(f"*Resources: {', '.join(summary)}*\n")

    return "\n".join(lines)


def render_no_changes() -> str:
    return (
        "## 📊 App Graph Diff\n\n"
        "No app graph changes detected.\n"
    )


def render_full_comment(sections: list[str]) -> str:
    header = "## 📊 App Graph Diff\n\n"
    footer = "\n---\n*Auto-generated by PR Graph Diff — comparing `.radius/app-graph.json`*\n"
    return header + "\n".join(sections) + footer


# ── main ─────────────────────────────────────────────────────────────

def main():
    graph_files_raw = os.environ.get("GRAPH_FILES", "").strip()
    base_sha = os.environ.get("BASE_SHA", "")
    head_sha = os.environ.get("HEAD_SHA", "")
    output_path = os.environ.get("DIFF_OUTPUT", "")

    if not base_sha or not head_sha:
        print("Error: BASE_SHA and HEAD_SHA must be set.", file=sys.stderr)
        sys.exit(1)

    # If no graph files changed, output "no changes"
    if not graph_files_raw:
        result = render_no_changes()
    else:
        graph_files = [f.strip() for f in graph_files_raw.splitlines() if f.strip()]
        sections: list[str] = []

        for gf in graph_files:
            base_raw = git_show(base_sha, gf)
            head_raw = git_show(head_sha, gf)

            base_graph = parse_graph(base_raw)
            head_graph = parse_graph(head_raw)

            diff = diff_graphs(base_graph, head_graph)
            sections.append(render_diff_section(gf, base_graph, head_graph, diff))

        result = render_full_comment(sections)

    # Output
    if output_path:
        with open(output_path, "w") as f:
            f.write(result)
        print(f"Diff written to {output_path}")
    else:
        print(result)


if __name__ == "__main__":
    main()
