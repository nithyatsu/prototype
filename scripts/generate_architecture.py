#!/usr/bin/env python3
"""
Parse app.bicep and generate an interactive architecture diagram using Mermaid.

GitHub natively renders Mermaid code blocks in markdown, and Mermaid supports
click directives that turn nodes into hyperlinks. This means the diagram
embedded directly in the README has clickable nodes - each one opens app.bicep
at the line where that resource is defined.

No external HTML page, no image maps, no GitHub Pages needed.
"""

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
                     "'lineColor': '#656d76', "
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
    lines.append("    classDef container fill:#ddf4ff,stroke:#218bff,stroke-width:1.5px,color:#1f2328,rx:6,ry:6")
    # Datastore: orange accent (like GitHub's warning/merge colors)
    lines.append("    classDef datastore fill:#fff8c5,stroke:#d4a72c,stroke-width:1.5px,color:#1f2328,rx:6,ry:6")
    # Other: neutral gray
    lines.append("    classDef other fill:#f6f8fa,stroke:#d1d9e0,stroke-width:1.5px,color:#1f2328,rx:6,ry:6")

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
        tooltip = "{} — {} line {}".format(res["display_name"], bicep_file, res["line_number"])
        lines.append('    click {} "{}" "{}"'.format(res["symbolic_name"], url, tooltip))

    # Link style — GitHub gray, clean
    edge_count = 0
    for conn in connections:
        if conn["from"] in resource_map and conn["to"] in resource_map:
            from_res = resource_map[conn["from"]]
            to_res = resource_map[conn["to"]]
            if from_res["category"] == "application" or to_res["category"] == "application":
                continue
            lines.append("    linkStyle {} stroke:#656d76,stroke-width:1.5px".format(edge_count))
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

    if not os.path.exists(bicep_path):
        print(f"Error: {bicep_path} not found")
        sys.exit(1)

    print(f"Parsing {bicep_path}...")
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
