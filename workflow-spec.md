# Workflow Specification

> Fill in the sections below to describe what the CI/CD workflow should do.
> Then ask Copilot: "Implement a GitHub Actions workflow based on workflow-spec.md"

## Trigger

The workflow should run every 2 hours. I should also be able to run it manually. 

## Requirements

# Workflow Specification

> Fill in the sections below to describe what the CI/CD workflow should do.
> Then ask Copilot: "Implement a GitHub Actions workflow based on workflow-spec.md"

## Trigger

- **Schedule:** Every 2 hours (`cron: '0 */2 * * *'`)
- **Manual:** `workflow_dispatch`

## Requirements

### 1. Spin up a Kind cluster

Create an ephemeral Kubernetes cluster using [Kind](https://kind.sigs.k8s.io/).

### 2. Install Radius

Install Radius into the Kind cluster using custom images:

```bash
rad install kubernetes \
    --set rp.image=ghcr.io/nithyatsu/applications-rp,rp.tag=latest \
    --set dynamicrp.image=ghcr.io/nithyatsu/dynamic-rp,dynamicrp.tag=latest \
    --set controller.image=ghcr.io/nithyatsu/controller,controller.tag=latest \
    --set ucp.image=ghcr.io/nithyatsu/ucpd,ucp.tag=latest \
    --set bicep.image=ghcr.io/nithyatsu/bicep,bicep.tag=latest
```

### 3. Verify Radius is ready

Run `rad group create test` and confirm it succeeds. This validates that all Radius pods are healthy and the control plane is operational.

### 4. Generate the application graph

Run `rad app graph <fully-qualified-path-to-app.bicep>`.

- The command requires an **absolute file path** (e.g., `${{ github.workspace }}/app.bicep`).
- The command outputs a structured representation of the application's resources and their connections.
- The command gets updated all the time. Try it out, update the workflow to work with the latest behavior. 

### 5. Build a visual graph from the output

Parse the output from step 4 and construct a renderable graph (e.g., using Graphviz or Mermaid). Extract:

- **Nodes** — each resource (name, type, source file, line number)
- **Edges** — connections between resources

### 6. Render the graph and update the README

Generate a **Mermaid diagram** and embed it directly in the `README.md` Architecture section as a fenced `mermaid` code block. GitHub renders Mermaid natively, so the diagram is interactive right in the README — no separate image files or HTML pages needed.

#### Format

Use a Mermaid `graph LR` with:
- `%%{ init }%%` directive for theme configuration
- `classDef` for node styling
- `click` directives for making each node a hyperlink with tooltip

#### Visual style

| Property        | Value                                          |
|-----------------|-------------------------------------------------|
| Theme           | `base` (light)                                 |
| Background      | White (`#ffffff`)                               |
| Font color      | Dark (`#1f2328`)                               |
| Node shape      | Rounded-corner rectangles (`rx:6, ry:6`)        |
| Container border| Green (`#2da44e`)                               |
| Datastore border| Amber (`#d4a72c`)                               |
| Node fill       | White (`#ffffff`)                               |
| Edge color      | Green (`#2da44e`)                               |
| Font            | `-apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans", Helvetica, Arial, sans-serif` |

#### Interactivity (via Mermaid `click` directive)

| Feature         | Behavior                                        |
|-----------------|-------------------------------------------------|
| **Tooltip**     | Hovering a node shows: `"<name> — app.bicep line <N>"` |
| **Click**       | Clicking a node opens `https://github.com/<owner>/<repo>/blob/<branch>/app.bicep#L<N>` with the line highlighted |

#### README update

Replace the Architecture section's Mermaid code block with the newly generated one. The diagram should be the only content between the `## Architecture` heading and the next `##` heading.

### 7. Commit and push

Auto-commit changes to `docs/` and `README.md` only if the graph has changed.