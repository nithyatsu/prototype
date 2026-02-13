#!/usr/bin/env python3
"""
Compare app-graph.json between base and head commits and produce a
Markdown PR comment with:
  - Side-by-side Mermaid graphs (main vs PR)
  - A color-coded diff graph (green=added, amber=modified, red=removed)
  - Clickable nodes linking to the PR diff page
  - Resources/connections change table
  - "Powered by Radius" footer

Usage (CI):
    python scripts/graph_diff.py

Environment variables:
    GRAPH_FILES  — newline-separated list of .radius/app-graph.json paths
                   that changed in this PR (set by the workflow).
    BASE_SHA     — base commit SHA (PR target branch).
    HEAD_SHA     — head commit SHA (PR source branch).
    DIFF_OUTPUT  — path to write the Markdown output (default: stdout).
    PR_NUMBER    — PR number for building diff URLs.
    REPO_OWNER   — repository owner (e.g. "nithyatsu").
    REPO_NAME    — repository name (e.g. "prototype").
"""

import json
import os
import re
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


def resolve_name(res_id: str, resources: dict) -> str:
    """Get a short display name from a resource id or target string."""
    if res_id in resources:
        return resources[res_id].get("name", res_id)
    # ARM expression like [reference('database').id]
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


def categorize(res_type: str) -> str:
    """Categorize a resource type."""
    t = res_type.lower()
    if "containers" in t:
        return "container"
    elif any(ds in t for ds in ["rediscaches", "sqldatabases", "mongodatabases"]):
        return "datastore"
    elif "applications" in t and "containers" not in t:
        return "application"
    return "other"


def safe_node_id(name: str) -> str:
    """Make a Mermaid-safe node id."""
    return name.replace("-", "_").replace(".", "_")


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


# ── mermaid generation ───────────────────────────────────────────────

def make_mermaid_graph(resources: dict, connections: list) -> str:
    """Generate a simple Mermaid graph from resources and connections."""
    lines = []
    lines.append("%%{ init: { 'theme': 'base', 'themeVariables': { "
                 "'primaryColor': '#ffffff', "
                 "'primaryTextColor': '#1f2328', "
                 "'primaryBorderColor': '#d1d9e0', "
                 "'lineColor': '#2da44e', "
                 "'background': '#ffffff', "
                 "'mainBkg': '#ffffff', "
                 "'fontSize': '13px'"
                 " } } }%%")
    lines.append("graph LR")
    lines.append("    classDef container fill:#ffffff,stroke:#2da44e,stroke-width:1.5px,color:#1f2328,rx:6,ry:6")
    lines.append("    classDef datastore fill:#ffffff,stroke:#d4a72c,stroke-width:1.5px,color:#1f2328,rx:6,ry:6")
    lines.append("    classDef other fill:#ffffff,stroke:#d1d9e0,stroke-width:1.5px,color:#1f2328,rx:6,ry:6")

    for rid, res in resources.items():
        name = res.get("name", "unknown")
        res_type = res.get("type", "")
        cat = categorize(res_type)
        if cat == "application":
            continue
        nid = safe_node_id(name)
        lines.append('    {}["{}"]:::{}'.format(nid, name, cat))

    for src_id, tgt_id in connections:
        src = resolve_name(src_id, resources)
        tgt = resolve_name(tgt_id, resources)
        src_res = resources.get(src_id, {})
        tgt_res = resources.get(tgt_id, {})
        if categorize(src_res.get("type", "")) == "application":
            continue
        if categorize(tgt_res.get("type", "")) == "application":
            continue
        if src != tgt:
            lines.append("    {} --> {}".format(safe_node_id(src), safe_node_id(tgt)))

    return "\n".join(lines)


def make_diff_mermaid(base: dict, head: dict, diff: dict,
                      repo_owner: str, repo_name: str, pr_number: str) -> str:
    """Generate a color-coded diff Mermaid graph.

    Colors:
      - Green: added
      - Amber: modified
      - Red dashed: removed
      - Gray: unchanged
    Clicking a node opens the PR diff page anchored to the source file.
    """
    lines = []
    lines.append("%%{ init: { 'theme': 'base', 'themeVariables': { "
                 "'primaryColor': '#ffffff', "
                 "'primaryTextColor': '#1f2328', "
                 "'primaryBorderColor': '#d1d9e0', "
                 "'lineColor': '#656d76', "
                 "'background': '#ffffff', "
                 "'mainBkg': '#ffffff', "
                 "'fontSize': '13px'"
                 " } } }%%")
    lines.append("graph LR")

    # Class definitions for diff states
    lines.append("    classDef added fill:#dafbe1,stroke:#1a7f37,stroke-width:2px,color:#1a7f37,rx:6,ry:6")
    lines.append("    classDef modified fill:#fff8c5,stroke:#d4a72c,stroke-width:2px,color:#9a6700,rx:6,ry:6")
    lines.append("    classDef removed fill:#ffebe9,stroke:#d1242f,stroke-width:2px,stroke-dasharray:5 5,color:#d1242f,rx:6,ry:6")
    lines.append("    classDef unchanged fill:#ffffff,stroke:#d1d9e0,stroke-width:1px,color:#656d76,rx:6,ry:6")

    all_resources = {**base["resources"], **head["resources"]}
    diff_url = f"https://github.com/{repo_owner}/{repo_name}/pull/{pr_number}/files"

    all_rids = sorted(set(list(head["resources"].keys()) + list(base["resources"].keys())))
    nodes_added = set()

    for rid in all_rids:
        res = all_resources.get(rid, {})
        name = res.get("name", "unknown")
        res_type = res.get("type", "")

        if categorize(res_type) == "application":
            continue

        if rid in diff["added"]:
            status = "added"
            label = f"+ {name}"
        elif rid in diff["removed"]:
            status = "removed"
            label = f"- {name}"
        elif rid in diff["modified"]:
            status = "modified"
            label = f"~ {name}"
        else:
            status = "unchanged"
            label = name

        nid = safe_node_id(name)
        if nid not in nodes_added:
            lines.append('    {}["{}"]:::{}'.format(nid, label, status))
            nodes_added.add(nid)

    # Edges — union of base and head connections
    all_conns = set(head["connections"]) | set(base["connections"])
    for src_id, tgt_id in sorted(all_conns):
        src = resolve_name(src_id, all_resources)
        tgt = resolve_name(tgt_id, all_resources)
        src_res = all_resources.get(src_id, {})
        tgt_res = all_resources.get(tgt_id, {})
        if categorize(src_res.get("type", "")) == "application":
            continue
        if categorize(tgt_res.get("type", "")) == "application":
            continue
        if src == tgt:
            continue

        s = safe_node_id(src)
        t = safe_node_id(tgt)

        conn_tuple = (src_id, tgt_id)
        if conn_tuple in diff.get("added_conns", set()):
            lines.append("    {} -. new .-> {}".format(s, t))
        elif conn_tuple in diff.get("removed_conns", set()):
            lines.append("    {} -. removed .-> {}".format(s, t))
        else:
            lines.append("    {} --> {}".format(s, t))

    # Click directives — link to PR diff page anchored to the source file
    for rid in all_rids:
        res = all_resources.get(rid, {})
        name = res.get("name", "unknown")
        if categorize(res.get("type", "")) == "application":
            continue

        nid = safe_node_id(name)
        source_file = res.get("sourceLocation", {}).get("file", "")
        if source_file:
            file_url = f"{diff_url}#diff-{source_file.replace('/', '-').replace('.', '-')}"
            lines.append('    click {} href "{}" "View diff" _blank'.format(nid, file_url))

    return "\n".join(lines)


# ── markdown rendering ──────────────────────────────────────────────

def render_diff_section(app_path: str, base_graph: dict, head_graph: dict, diff: dict,
                        repo_owner: str, repo_name: str, pr_number: str) -> str:
    """Render a full Markdown section for one application's diff."""
    lines = []
    app_label = app_path.replace("/.radius/app-graph.json", "").replace(".radius/app-graph.json", "") or "(root)"
    lines.append(f"### 📦 `{app_label}`\n")

    has_changes = (diff["added"] or diff["removed"] or diff["modified"]
                   or diff["added_conns"] or diff["removed_conns"])

    if not has_changes:
        lines.append("> No resource or connection changes.\n")
        return "\n".join(lines)

    # ── Side-by-side graphs ──
    base_mermaid = make_mermaid_graph(base_graph["resources"], base_graph["connections"])
    head_mermaid = make_mermaid_graph(head_graph["resources"], head_graph["connections"])

    lines.append("<table>")
    lines.append("<tr><th>📌 main</th><th>🔀 This PR</th></tr>")
    lines.append("<tr><td>\n")
    lines.append("```mermaid")
    lines.append(base_mermaid)
    lines.append("```")
    lines.append("\n</td><td>\n")
    lines.append("```mermaid")
    lines.append(head_mermaid)
    lines.append("```")
    lines.append("\n</td></tr>")
    lines.append("</table>\n")

    # ── Diff graph ──
    diff_mermaid = make_diff_mermaid(base_graph, head_graph, diff,
                                     repo_owner, repo_name, pr_number)
    lines.append("#### Diff\n")
    lines.append("🟢 Added  🟡 Modified  🔴 Removed\n")
    lines.append("```mermaid")
    lines.append(diff_mermaid)
    lines.append("```\n")

    # ── Resources table ──
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

    # ── Connections table ──
    all_resources = {**base_graph["resources"], **head_graph["resources"]}
    if diff["added_conns"] or diff["removed_conns"]:
        lines.append("#### Connections\n")
        lines.append("| Status | Connection |")
        lines.append("|--------|------------|")
        for src, tgt in sorted(diff["added_conns"]):
            lines.append(f"| 🟢 Added | {resolve_name(src, all_resources)} → {resolve_name(tgt, all_resources)} |")
        for src, tgt in sorted(diff["removed_conns"]):
            lines.append(f"| 🔴 Removed | {resolve_name(src, all_resources)} → {resolve_name(tgt, all_resources)} |")
        lines.append("")

    # Summary
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
        "> No app graph changes detected.\n\n"
        "---\n"
        "*Powered by [Radius](https://radapp.io/)*\n"
    )


def render_full_comment(sections: list) -> str:
    header = "## 📊 App Graph Diff\n\n"
    footer = "\n---\n*Powered by [Radius](https://radapp.io/)*\n"
    return header + "\n".join(sections) + footer


# ── main ─────────────────────────────────────────────────────────────

def main():
    graph_files_raw = os.environ.get("GRAPH_FILES", "").strip()
    base_sha = os.environ.get("BASE_SHA", "")
    head_sha = os.environ.get("HEAD_SHA", "")
    output_path = os.environ.get("DIFF_OUTPUT", "")
    pr_number = os.environ.get("PR_NUMBER", "0")
    repo_owner = os.environ.get("REPO_OWNER", "nithyatsu")
    repo_name = os.environ.get("REPO_NAME", "prototype")

    if not base_sha or not head_sha:
        print("Error: BASE_SHA and HEAD_SHA must be set.", file=sys.stderr)
        sys.exit(1)

    # If no graph files changed, output "no changes"
    if not graph_files_raw:
        result = render_no_changes()
    else:
        graph_files = [f.strip() for f in graph_files_raw.splitlines() if f.strip()]
        sections = []

        for gf in graph_files:
            base_raw = git_show(base_sha, gf)
            head_raw = git_show(head_sha, gf)

            base_graph = parse_graph(base_raw)
            head_graph = parse_graph(head_raw)

            diff = diff_graphs(base_graph, head_graph)
            sections.append(render_diff_section(
                gf, base_graph, head_graph, diff,
                repo_owner, repo_name, pr_number,
            ))

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
