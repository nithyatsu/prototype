#!/usr/bin/env python3
"""
Generate an interactive Mermaid architecture diagram for README.md.

Two modes of operation:
  1. **rad app graph** (primary) — reads structured output from `rad app graph`
     via the RAD_GRAPH_OUTPUT env var. This is used in CI after Radius is
     installed in a Kind cluster.
  2. **Direct Bicep parsing** (fallback) — regex-parses app.bicep directly.
     Used locally or when `rad app graph` is not yet available.

The generated Mermaid diagram uses GitHub's visual style (white background,
rounded-corner nodes, green/amber borders) and has clickable nodes that open
the corresponding line in app.bicep on GitHub.
"""

import json
import re
import os
import sys


def parse_bicep(bicep_path):
    """Parse a Bicep file and extract resources, connections, and line numbers."""
    with open(bicep_path, "r") as f:
        content = f.read()

    resources = []
    connections = []

    resource_pattern = re.compile(
        r"resource\s+(\w+)\s+'([^']+)'\s*=\s*\{(.*?)\n\}",
        re.DOTALL,
    )

    for match in resource_pattern.finditer(content):
        symbolic_name = match.group(1)
        resource_type = match.group(2)
        body = match.group(3)

        line_number = content[: match.start()].count("\n") + 1

        name_match = re.search(r"name:\s*'([^']+)'", body)
        display_name = name_match.group(1) if name_match else symbolic_name

        image_match = re.search(r"image:\s*'([^']+)'", body)
        image = image_match.group(1) if image_match else None

        port_match = re.search(r"containerPort:\s*(\d+)", body)
        port = port_match.group(1) if port_match else None

        if "containers" in resource_type.lower():
            category = "container"
        elif "rediscaches" in resource_type.lower():
            category = "datastore"
        elif "sqldatabases" in resource_type.lower():
            category = "datastore"
        elif "mongodatabases" in resource_type.lower():
            category = "datastore"
        elif "applications" in resource_type.lower() and "containers" not in resource_type.lower():
            category = "application"
        else:
            category = "other"

        resources.append({
            "symbolic_name": symbolic_name,
            "display_name": display_name,
            "resource_type": resource_type,
            "image": image,
            "port": port,
            "category": category,
            "line_number": line_number,
        })

        conn_pattern = re.compile(r"connections:\s*\{(.*?)\n\s*\}", re.DOTALL)
        conn_match = conn_pattern.search(body)
        if conn_match:
            conn_body = conn_match.group(1)
            conn_entries = re.findall(r"(\w+):\s*\{", conn_body)
            for target in conn_entries:
                connections.append({"from": symbolic_name, "to": target})

        source_refs = re.findall(r"source:\s*(\w+)\.(id|connectionString)", body)
        for ref_name, _ in source_refs:
            conn = {"from": symbolic_name, "to": ref_name}
            if conn not in connections:
                connections.append(conn)

    return resources, connections


def parse_rad_graph_output(output_path):
    """Parse the output of `rad app graph` and extract resources and connections.

    Expected format (JSON): an object with "resources" and "connections" arrays, e.g.:
    {
      "resources": [
        {
          "id": "/planes/radius/local/resourceGroups/.../containers/frontend",
          "name": "frontend",
          "type": "Applications.Core/containers",
          "file": "app.bicep",
          "line": 18,
          "properties": { "image": "nginx:alpine", "port": 80 }
        },
        ...
      ],
      "connections": [
        {
          "sourceId": "/planes/radius/local/.../containers/frontend",
          "targetId": "http://backend:3000",
          "type": "connection"
        },
        {
          "sourceId": "/planes/radius/local/.../containers/frontend",
          "targetId": "app",
          "type": "dependsOn"
        },
        ...
      ]
    }

    If the output is not valid JSON, fall back to line-based parsing.
    """
    with open(output_path, "r") as f:
        raw = f.read().strip()

    resources = []
    connections = []

    try:
        data = json.loads(raw)

        # Build a lookup: resource id -> symbolic name
        id_to_name = {}

        for res in data.get("resources", []):
            name = res.get("name", "unknown")
            res_type = res.get("type", "")
            res_id = res.get("id", "")
            line_number = res.get("line", 0)
            props = res.get("properties", {})

            # Categorize
            if "containers" in res_type.lower():
                category = "container"
            elif "rediscaches" in res_type.lower() or "sqldatabases" in res_type.lower() or "mongodatabases" in res_type.lower():
                category = "datastore"
            elif "applications" in res_type.lower() and "containers" not in res_type.lower():
                category = "application"
            else:
                category = "other"

            resources.append({
                "symbolic_name": name,
                "display_name": name,
                "resource_type": res_type,
                "image": props.get("image"),
                "port": str(props["port"]) if props.get("port") else None,
                "category": category,
                "line_number": line_number,
            })

            if res_id:
                id_to_name[res_id] = name

            # Also handle per-resource connections list (legacy format)
            for target in res.get("connections", []):
                connections.append({"from": name, "to": target})

        # Parse top-level connections array (new format from rad app graph)
        for conn in data.get("connections", []):
            source_id = conn.get("sourceId", "")
            target_id = conn.get("targetId", "")
            conn_type = conn.get("type", "")

            # Skip dependsOn connections to the application resource
            if conn_type == "dependsOn":
                continue

            # Resolve sourceId to resource name
            source_name = id_to_name.get(source_id, "")
            if not source_name:
                # Try matching by the last segment of the id
                source_last = source_id.rstrip("/").rsplit("/", 1)[-1] if "/" in source_id else source_id
                for rid, rname in id_to_name.items():
                    if rid.endswith("/" + source_last):
                        source_name = rname
                        break

            # Resolve targetId to resource name
            target_name = id_to_name.get(target_id, "")
            if not target_name:
                # targetId might be a URL like "http://backend:3000" or a plain name like "app"
                # Extract hostname from URL if present
                url_match = re.match(r"https?://([^:/]+)", target_id)
                if url_match:
                    hostname = url_match.group(1)
                    # Match hostname to any resource name (may contain hostname as substring)
                    for rname in id_to_name.values():
                        if hostname in rname or rname in hostname:
                            target_name = rname
                            break
                    if not target_name:
                        # Use hostname itself as the target name
                        target_name = hostname
                else:
                    # Plain name — try direct match
                    target_last = target_id.rstrip("/").rsplit("/", 1)[-1] if "/" in target_id else target_id
                    for rid, rname in id_to_name.items():
                        if rid.endswith("/" + target_last) or rname == target_last:
                            target_name = rname
                            break
                    if not target_name:
                        target_name = target_last

            if source_name and target_name and source_name != target_name:
                conn_entry = {"from": source_name, "to": target_name}
                if conn_entry not in connections:
                    connections.append(conn_entry)

        print(f"Parsed rad app graph output: {len(resources)} resources, {len(connections)} connections")

    except (json.JSONDecodeError, KeyError) as e:
        print(f"Warning: Could not parse rad app graph output as JSON ({e})")
        print("Raw output:")
        print(raw[:500])
        print("\nFalling back to direct Bicep parsing...")
        return None, None

    return resources, connections


def get_github_file_url(repo_owner, repo_name, branch, file_path, line):
    """Build a GitHub URL that highlights a specific line."""
    return f"https://github.com/{repo_owner}/{repo_name}/blob/{branch}/{file_path}#L{line}"


def generate_mermaid(resources, connections, repo_owner, repo_name, branch, bicep_file):
    """Generate a Mermaid diagram string with clickable nodes and GitHub-like styling."""

    lines = ["graph LR"]

    # --- GitHub light theme styling ---
    # Matches GitHub's own dependency/action graph look:
    # white background, light gray borders, clean rounded-corner boxes
    lines.insert(0, "%%{ init: { 'theme': 'base', 'themeVariables': { "
                     "'primaryColor': '#ffffff', "
                     "'primaryTextColor': '#1f2328', "
                     "'primaryBorderColor': '#d1d9e0', "
                     "'lineColor': '#2da44e', "
                     "'secondaryColor': '#f6f8fa', "
                     "'tertiaryColor': '#ffffff', "
                     "'background': '#ffffff', "
                     "'mainBkg': '#ffffff', "
                     "'nodeBorder': '#d1d9e0', "
                     "'clusterBkg': '#f6f8fa', "
                     "'clusterBorder': '#d1d9e0', "
                     "'fontSize': '14px', "
                     "'fontFamily': '-apple-system, BlinkMacSystemFont, Segoe UI, Noto Sans, Helvetica, Arial, sans-serif'"
                     " } } }%%")

    # Class definitions — GitHub light palette with rounded corners
    # Container: blue accent (like GitHub's blue links/actions)
    lines.append("    classDef container fill:#ffffff,stroke:#2da44e,stroke-width:1.5px,color:#1f2328,rx:6,ry:6")
    # Datastore: orange accent (like GitHub's warning/merge colors)
    lines.append("    classDef datastore fill:#ffffff,stroke:#d4a72c,stroke-width:1.5px,color:#1f2328,rx:6,ry:6")
    # Other: neutral gray
    lines.append("    classDef other fill:#ffffff,stroke:#d1d9e0,stroke-width:1.5px,color:#1f2328,rx:6,ry:6")

    resource_map = {r["symbolic_name"]: r for r in resources}

    # Add nodes (skip the top-level application resource)
    # Use regular box nodes [" "] — rounded corners come from rx/ry in classDef
    for res in resources:
        if res["category"] == "application":
            continue

        # Build label — clean, no line numbers (those go in tooltip only)
        label_parts = ["<b>" + res["display_name"] + "</b>"]
        if res["image"]:
            label_parts.append(res["image"])
        if res["port"]:
            label_parts.append(":" + res["port"])

        label = "<br/>".join(label_parts)
        lines.append('    {}["{}"]:::{}'.format(res["symbolic_name"], label, res["category"]))

    # Add edges — clean arrow style
    for conn in connections:
        if conn["from"] in resource_map and conn["to"] in resource_map:
            from_res = resource_map[conn["from"]]
            to_res = resource_map[conn["to"]]
            if from_res["category"] == "application" or to_res["category"] == "application":
                continue
            lines.append("    {} --> {}".format(conn["from"], conn["to"]))

    # Add click directives — tooltip shows line number, click opens GitHub
    for res in resources:
        if res["category"] == "application":
            continue
        url = get_github_file_url(repo_owner, repo_name, branch, bicep_file, res["line_number"])
        tooltip = "{}:{}" .format(bicep_file, res["line_number"])
        lines.append('    click {} href "{}" "{}" _blank'.format(res["symbolic_name"], url, tooltip))

    # Link style — GitHub gray, clean
    edge_count = 0
    for conn in connections:
        if conn["from"] in resource_map and conn["to"] in resource_map:
            from_res = resource_map[conn["from"]]
            to_res = resource_map[conn["to"]]
            if from_res["category"] == "application" or to_res["category"] == "application":
                continue
            lines.append("    linkStyle {} stroke:#2da44e,stroke-width:1.5px".format(edge_count))
            edge_count += 1

    return "\n".join(lines)


def update_readme(readme_path, mermaid_block):
    """Update the Architecture section in README.md with the Mermaid diagram."""
    with open(readme_path, "r") as f:
        content = f.read()

    # Build the new Architecture section body
    new_body = "\n".join([
        "",
        "> *Auto-generated from `app.bicep` \u2014 click any node to jump to its definition in the source.*",
        "",
        "```mermaid",
        mermaid_block,
        "```",
        "",
    ])

    # Replace the Architecture section content
    pattern = re.compile(
        r"(## Architecture\s*\n).*?(\n## |\Z)",
        re.DOTALL,
    )

    if pattern.search(content):
        new_content = pattern.sub(r"\1" + new_body + "\n" + r"\2", content)
    else:
        new_content = content + "\n## Architecture\n" + new_body + "\n"

    with open(readme_path, "w") as f:
        f.write(new_content)

    print("README.md updated")


def main():
    repo_root = os.environ.get(
        "GITHUB_WORKSPACE",
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    )
    bicep_file = "app.bicep"
    bicep_path = os.path.join(repo_root, bicep_file)
    readme_path = os.path.join(repo_root, "README.md")

    # Repository info for building GitHub URLs for clickable nodes
    repo_owner = os.environ.get("REPO_OWNER", "nithyatsu")
    repo_name = os.environ.get("REPO_NAME", "prototype")
    branch = os.environ.get("REPO_BRANCH", "main")

    # --- Try rad app graph output first (primary path in CI) ---
    rad_graph_output = os.environ.get("RAD_GRAPH_OUTPUT")
    resources = None
    connections = None

    if rad_graph_output and os.path.exists(rad_graph_output):
        print(f"Reading rad app graph output from {rad_graph_output}...")
        resources, connections = parse_rad_graph_output(rad_graph_output)

    # --- Fallback: parse Bicep directly ---
    if resources is None:
        if not os.path.exists(bicep_path):
            print(f"Error: {bicep_path} not found")
            sys.exit(1)

        print(f"Parsing {bicep_path} directly (fallback mode)...")
        resources, connections = parse_bicep(bicep_path)

    print(f"Found {len(resources)} resources and {len(connections)} connections")
    for r in resources:
        print("  - {} ({}) @ line {}".format(r["display_name"], r["category"], r["line_number"]))
    for c in connections:
        print("  - {} -> {}".format(c["from"], c["to"]))

    print("\nGenerating Mermaid diagram...")
    mermaid_block = generate_mermaid(
        resources, connections,
        repo_owner, repo_name, branch, bicep_file,
    )

    print("\nMermaid output:")
    print(mermaid_block)

    print("\nUpdating README...")
    update_readme(readme_path, mermaid_block)

    print("Done!")


if __name__ == "__main__":
    main()
