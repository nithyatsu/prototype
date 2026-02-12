# Prototype App

A simple **Frontend → Backend → Database** application built with [Radius](https://radapp.io/) and Bicep.

## Architecture


> *Auto-generated from `app.bicep` — click any node to jump to its definition in the source.*

```mermaid
graph LR
    classDef container fill:#161b22,stroke:#58a6ff,stroke-width:2px,color:#e6edf3
    classDef datastore fill:#161b22,stroke:#f78166,stroke-width:2px,color:#e6edf3
    classDef other fill:#161b22,stroke:#8b949e,stroke-width:2px,color:#e6edf3
    frontend["frontend<br/>nginx:alpine<br/>port 80<br/>app.bicep L18"]:::container
    backend["backend<br/>node:18-alpine<br/>port 3000<br/>app.bicep L45"]:::container
    database["database<br/>app.bicep L75"]:::datastore
    frontend --> backend
    backend --> database
    click frontend "https://github.com/nithyatsu/prototype/blob/main/app.bicep#L18" "frontend defined at app.bicep line 18"
    click backend "https://github.com/nithyatsu/prototype/blob/main/app.bicep#L45" "backend defined at app.bicep line 45"
    click database "https://github.com/nithyatsu/prototype/blob/main/app.bicep#L75" "database defined at app.bicep line 75"
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
