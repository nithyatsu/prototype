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

---

## User Story 4 — PR Graph Diff (P2)

**Goal:** Show a visual diff of the app graph in PR comments so reviewers can see architectural impact without deploying.

**Depends on:** User Stories 1–3 being stable.

### Operational model

The GitHub Action reads committed `.radius/app-graph.json` files from git history — it does **not** generate graphs on-demand. No Bicep/Radius tooling is needed, keeping the Action lightweight and fast.

### Trigger events

| Event | Behavior |
|-------|----------|
| `pull_request` (every push) | Posts or updates a diff comment on the PR |
| `push` to `main` | Updates the baseline for historical comparison |

The comment is posted on **every push** to the PR, not just the first one. If no Bicep/graph changes exist, the comment says "No app graph changes detected."

### Monorepo support

Auto-detect all `**/.radius/app-graph.json` files. Each graph is diffed independently with separate comment sections per application.

### PR comment format

The comment includes:

1. **Side-by-side Mermaid graphs** — `main` graph on the left, PR graph on the right, for visual comparison.
2. **Diff graph** — a single Mermaid graph using color-coded nodes:
   - 🟢 Green border — added resources
   - 🟡 Amber border — modified resources
   - 🔴 Red border — removed resources
   - Gray border — unchanged resources
3. **Clickable nodes** — clicking a node opens the PR's diff page (`/files`) with the resource's Bicep section in focus (anchored to the diff line).
4. **Resources & connections table** — lists added/removed/modified resources and connections.
5. **Footer** — "Powered by [Radius](https://radapp.io/)"

### Acceptance criteria

1. PR includes changes to `.radius/app-graph.json` → Action posts a comment with side-by-side graphs + diff graph.
2. PR has no Bicep or graph changes → Comment says "No app graph changes detected."
3. PR adds a new connection → Diff graph shows the new edge; new resource node is green.
4. PR removes a resource → Diff graph shows the removed node in red (dashed border).
5. PR modifies a resource → Diff graph shows the modified node in amber.
6. PR comment already exists from a previous push → Existing comment is updated, not duplicated.
7. Clicking a node in the diff graph opens the PR diff page with the resource's section in focus.
8. Bicep files changed but `.radius/app-graph.json` was not updated → CI validation fails with instructions.
9. Monorepo with multiple apps → Unified comment with separate sections per application.
10. Comment footer says "Powered by [Radius](https://radapp.io/)".