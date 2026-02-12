#!/usr/bin/env python3
"""
Parse app.bicep and generate an interactive architecture diagram.

GitHub's markdown renderer sanitizes SVGs and strips <a> links, so simple
SVG embedding with hyperlinks won't produce clickable nodes. Instead we:

  1. Render the graph as SVG via Graphviz (with URL/tooltip attributes).
  2. Also render a CMAPX (client-side HTML image map) from the same graph.
  3. Render a PNG version of the graph for the image map to reference.
  4. Write an HTML file (docs/architecture.html) that combines the PNG +
     image map so each node is a clickable region linking to the correct
     line in app.bicep on GitHub.
  5. Update README.md with a PNG preview and a link to the interactive HTML.

The interactive HTML can be viewed via GitHub Pages or by opening the raw
file locally.
"""

import re
import os
import sys
import subprocess
from pathlib import Path

try:
    import graphviz
except ImportError:
    print("Installing graphviz python package...")
    os.system(f"{sys.executable} -m pip install graphviz")
    import graphviz


def parse_bicep(bicep_path: str) -> tuple[list[dict], list[dict]]:
    """Parse a Bicep file and extract resources, connections, and line numbers."""
    with open(bicep_path, "r") as f:
        content = f.read()

    resources = []
    connections = []

    # Match resource blocks: resource <symbolic_name> '<type>' = {
    resource_pattern = re.compile(
        r"resource\s+(\w+)\s+'([^']+)'\s*=\s*\{(.*?)\n\}",
        re.DOTALL,
    )

    for match in resource_pattern.finditer(content):
        symbolic_name = match.group(1)
        resource_type = match.group(2)
        body = match.group(3)

        # Calculate the 1-based line number where this resource is defined
        line_number = content[: match.start()].count("\n") + 1

        # Extract the 'name' property
        name_match = re.search(r"name:\s*'([^']+)'", body)
        display_name = name_match.group(1) if name_match else symbolic_name

        # Extract image if present
        image_match = re.search(r"image:\s*'([^']+)'", body)
        image = image_match.group(1) if image_match else None

        # Extract container port
        port_match = re.search(r"containerPort:\s*(\d+)", body)
        port = port_match.group(1) if port_match else None

        # Determine resource category
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

        # Extract connections from the body
        conn_pattern = re.compile(r"connections:\s*\{(.*?)\n\s*\}", re.DOTALL)
        conn_match = conn_pattern.search(body)
        if conn_match:
            conn_body = conn_match.group(1)
            conn_entries = re.findall(r"(\w+):\s*\{", conn_body)
            for target in conn_entries:
                connections.append({
                    "from": symbolic_name,
                    "to": target,
                })

        # Extract connections via source references like database.id
        source_refs = re.findall(r"source:\s*(\w+)\.(id|connectionString)", body)
        for ref_name, _ in source_refs:
            conn = {"from": symbolic_name, "to": ref_name}
            if conn not in connections:
                connections.append(conn)

    return resources, connections


def get_github_file_url(repo_owner: str, repo_name: str, branch: str, file_path: str, line: int) -> str:
    """Build a GitHub URL that highlights a specific line."""
    return f"https://github.com/{repo_owner}/{repo_name}/blob/{branch}/{file_path}#L{line}"


def generate_graph(
    resources: list[dict],
    connections: list[dict],
    output_dir: str,
    repo_owner: str,
    repo_name: str,
    branch: str,
    bicep_file: str,
):
    """Generate a PNG diagram, an SVG with links, and an HTML page with an image map."""

    dot = graphviz.Digraph(
        "architecture",
        engine="dot",
    )

    # GitHub-inspired global styling
    dot.attr(
        rankdir="LR",
        bgcolor="#0d1117",
        fontname="Segoe UI, Helvetica, Arial, sans-serif",
        fontcolor="#e6edf3",
        pad="0.5",
        nodesep="1",
        ranksep="1.5",
        label=f"Architecture \u00b7 {bicep_file}",
        labelloc="t",
        fontsize="18",
        style="rounded",
    )

    # Default node styling (GitHub dark theme)
    dot.attr(
        "node",
        shape="box",
        style="filled,rounded",
        fillcolor="#161b22",
        color="#30363d",
        fontcolor="#e6edf3",
        fontname="Segoe UI, Helvetica, Arial, sans-serif",
        fontsize="12",
        margin="0.3,0.2",
        penwidth="1.5",
    )

    # Default edge styling
    dot.attr(
        "edge",
        color="#58a6ff",
        fontcolor="#8b949e",
        fontname="Segoe UI, Helvetica, Arial, sans-serif",
        fontsize="10",
        arrowsize="0.8",
        penwidth="1.5",
    )

    # Color scheme per category (GitHub palette)
    category_colors = {
        "container": {"fillcolor": "#161b22", "color": "#58a6ff"},   # Blue border
        "datastore": {"fillcolor": "#161b22", "color": "#f78166"},   # Orange border
        "application": {"fillcolor": "#161b22", "color": "#3fb950"}, # Green border
        "other": {"fillcolor": "#161b22", "color": "#8b949e"},       # Gray border
    }

    # Build a lookup from symbolic_name -> resource
    resource_map = {r["symbolic_name"]: r for r in resources}

    # Add nodes (skip the top-level application resource)
    for res in resources:
        if res["category"] == "application":
            continue

        colors = category_colors.get(res["category"], category_colors["other"])

        # Build label
        lines = [f"{res['display_name']}"]
        if res["image"]:
            lines.append(f"{res['image']}")
        if res["port"]:
            lines.append(f":{res['port']}")

        label = "\\n".join(lines)

        # GitHub URL for this resource's line
        url = get_github_file_url(repo_owner, repo_name, branch, bicep_file, res["line_number"])
        tooltip = f"{res['display_name']} \u2014 {bicep_file} line {res['line_number']}"

        dot.node(
            res["symbolic_name"],
            label=label,
            fillcolor=colors["fillcolor"],
            color=colors["color"],
            penwidth="2",
            URL=url,
            tooltip=tooltip,
            target="_blank",
        )

    # Add edges
    for conn in connections:
        if conn["from"] in resource_map and conn["to"] in resource_map:
            from_res = resource_map[conn["from"]]
            to_res = resource_map[conn["to"]]
            if from_res["category"] == "application" or to_res["category"] == "application":
                continue
            dot.edge(conn["from"], conn["to"])

    # Ensure output directory exists
    os.makedirs(output_dir, exist_ok=True)

    dot_path = os.path.join(output_dir, "architecture.dot")
    dot.save(dot_path)

    # --- 1. Render PNG ---
    png_path = os.path.join(output_dir, "architecture.png")
    dot.format = "png"
    dot.render(os.path.join(output_dir, "architecture"), cleanup=False)
    print(f"  PNG saved to {png_path}")

    # --- 2. Render SVG (with embedded links for local/raw viewing) ---
    svg_path = os.path.join(output_dir, "architecture.svg")
    dot.format = "svg"
    dot.render(os.path.join(output_dir, "architecture"), cleanup=False)
    print(f"  SVG saved to {svg_path}")

    # --- 3. Render CMAPX (HTML image map) ---
    cmapx_result = subprocess.run(
        ["dot", "-Tcmapx", dot_path],
        capture_output=True, text=True, check=True,
    )
    image_map = cmapx_result.stdout
    print(f"  Image map generated")

    # --- 4. Build interactive HTML page ---
    html_path = os.path.join(output_dir, "architecture.html")
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Architecture \u00b7 {bicep_file}</title>
  <style>
    body {{
      margin: 0;
      padding: 24px;
      background: #0d1117;
      color: #e6edf3;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
      display: flex;
      flex-direction: column;
      align-items: center;
    }}
    h1 {{
      font-size: 20px;
      font-weight: 600;
      margin-bottom: 8px;
      color: #e6edf3;
    }}
    p {{
      font-size: 14px;
      color: #8b949e;
      margin-bottom: 24px;
    }}
    .diagram-container {{
      border: 1px solid #30363d;
      border-radius: 6px;
      padding: 16px;
      background: #161b22;
      display: inline-block;
    }}
    img {{
      max-width: 100%;
      height: auto;
    }}
    a {{ color: #58a6ff; }}
  </style>
</head>
<body>
  <h1>Architecture \u00b7 {bicep_file}</h1>
  <p>Click any node to open <a href="https://github.com/{repo_owner}/{repo_name}/blob/{branch}/{bicep_file}">{bicep_file}</a> at the corresponding line.</p>
  <div class="diagram-container">
    <img src="architecture.png" usemap="#architecture" alt="Architecture Diagram">
    {image_map}
  </div>
</body>
</html>
"""
    with open(html_path, "w") as f:
        f.write(html_content)
    print(f"  HTML saved to {html_path}")

    # Clean up dot file
    if os.path.exists(dot_path):
        os.remove(dot_path)

    return png_path, svg_path, html_path


def update_readme(readme_path: str, png_rel_path: str, html_rel_path: str):
    """Update the Architecture section in README.md with the diagram and interactive link."""
    with open(readme_path, "r") as f:
        content = f.read()

    # Replace the Architecture section content
    pattern = re.compile(
        r"(## Architecture\s*\n).*?(\n## |\Z)",
        re.DOTALL,
    )

    note = (
        "> *Auto-generated every 2 hours from `app.bicep`.*\n"
        "> \n"
        f"> **[\U0001f449 Click here for the interactive version]({html_rel_path})** "
        "— click any node to jump to its definition in the source."
    )

    replacement_content = (
        f"\\1\n"
        f"![Architecture Diagram]({png_rel_path})\n\n"
        f"{note}\n"
        f"\n"
        f"\\2"
    )

    if pattern.search(content):
        new_content = pattern.sub(replacement_content, content)
    else:
        new_content = content + (
            f"\n## Architecture\n\n"
            f"![Architecture Diagram]({png_rel_path})\n\n"
            f"{note}\n"
        )

    with open(readme_path, "w") as f:
        f.write(new_content)

    print(f"README.md updated")


def main():
    repo_root = os.environ.get("GITHUB_WORKSPACE", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    bicep_file = "app.bicep"
    bicep_path = os.path.join(repo_root, bicep_file)
    output_dir = os.path.join(repo_root, "docs")
    readme_path = os.path.join(repo_root, "README.md")

    # Repository info — used to build GitHub URLs for clickable nodes
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
        print(f"  - {r['display_name']} ({r['category']}) @ line {r['line_number']}")
    for c in connections:
        print(f"  - {c['from']} \u2192 {c['to']}")

    print(f"\nGenerating diagram outputs...")
    png_path, svg_path, html_path = generate_graph(
        resources, connections, output_dir,
        repo_owner, repo_name, branch, bicep_file,
    )

    print(f"\nUpdating README...")
    update_readme(readme_path, "docs/architecture.png", "docs/architecture.html")

    print("Done!")


if __name__ == "__main__":
    main()
