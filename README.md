# Prototype App

A simple **Frontend → Backend → Database** application built with [Radius](https://radapp.io/) and Bicep.

## Architecture


> *Auto-generated from `app.bicep` — click any node to jump to its definition in the source.*

```mermaid
%%{ init: { 'theme': 'base', 'themeVariables': { 'primaryColor': '#ffffff', 'primaryTextColor': '#1f2328', 'primaryBorderColor': '#d1d9e0', 'lineColor': '#2da44e', 'secondaryColor': '#f6f8fa', 'tertiaryColor': '#ffffff', 'background': '#ffffff', 'mainBkg': '#ffffff', 'nodeBorder': '#d1d9e0', 'clusterBkg': '#f6f8fa', 'clusterBorder': '#d1d9e0', 'fontSize': '14px', 'fontFamily': '-apple-system, BlinkMacSystemFont, Segoe UI, Noto Sans, Helvetica, Arial, sans-serif' } } }%%
graph LR
    classDef container fill:#ffffff,stroke:#2da44e,stroke-width:1.5px,color:#1f2328,rx:6,ry:6
    classDef datastore fill:#ffffff,stroke:#d4a72c,stroke-width:1.5px,color:#1f2328,rx:6,ry:6
    classDef other fill:#ffffff,stroke:#d1d9e0,stroke-width:1.5px,color:#1f2328,rx:6,ry:6
    frontend["<b>frontend</b><br/>nginx:alpine<br/>:80"]:::container
    backend["<b>backend</b><br/>node:18-alpine<br/>:3000"]:::container
    database["<b>database</b>"]:::datastore
    frontend --> backend
    backend --> database
    click frontend "https://github.com/nithyatsu/prototype/blob/main/app.bicep#L18" "frontend — app.bicep line 18"
    click backend "https://github.com/nithyatsu/prototype/blob/main/app.bicep#L45" "backend — app.bicep line 45"
    click database "https://github.com/nithyatsu/prototype/blob/main/app.bicep#L75" "database — app.bicep line 75"
    linkStyle 0 stroke:#2da44e,stroke-width:1.5px
    linkStyle 1 stroke:#2da44e,stroke-width:1.5px
```


## Prerequisites

- [Radius CLI](https://docs.radapp.io/getting-started/) installed
- A Radius environment configured (e.g., local Kubernetes)

## Deploy

```bash
rad deploy app.bicep
```

## Project Structure

```
.
├── app.bicep            # Radius application definition
├── workflow-spec.md     # Workflow specification (CI/CD requirements)
└── README.md            # This file
```

## Workflow

See [workflow-spec.md](workflow-spec.md) to define CI/CD workflow requirements. Once authored, a GitHub Actions (or other CI/CD) workflow can be generated from it.
