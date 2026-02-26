# CodeCarbon MCP Server

This MCP server exposes CodeCarbon API capabilities to LLM clients through MCP tools and allow AI agents to run measurements locally thanks to CodeCarbon's library.

It is designed for a setup where the server runs with valid credentials and queries
experiment records directly from the official API.

## Features

- Read organizations, projects, and experiments from CodeCarbon API.
- Compute experiment consumption from run summaries.
- Recommend the least emitting experiment with an optional minimum accuracy.
- Provide demo prompt scenarios for Friday's presentation.
- Create 

## Requirements

- Python 3.12 
- pip 
- uv

## Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd mcp-cc
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

## Login Variables

Before running the server, at the root of the project, execute the command "codecarbon login" then login to your codecarbon account, a credential file will be generated at the root.

## Run

From repository root:

```bash
uv run server.py
```

The server will start and be ready to receive MCP client connections.

## MCP Tools

API tools:
- `check_auth`
- `list_organizations`
- `list_projects`
- `list_experiments`
- `get_experiment_consumption`
- `get_experiment_consumption_by_name`
- `recommend_lowest_emission_experiment`
- `demo_prompt_scenarios`
- `create_expriment`
Local tools:
- `start_tracking`
- `stop_tracking`
- `get_status`
- `get_current_metrics`

## Accuracy Constraint Notes

The `recommend_lowest_emission_experiment` tool can enforce `min_accuracy`, but the API
does not expose a dedicated accuracy field today. The server infers accuracy from
experiment `name` or `description` when formatted like:

- `accuracy=92.4`
- `accuracy: 92.4%`