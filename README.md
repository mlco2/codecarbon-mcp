# CodeCarbon MCP Server

This MCP server exposes CodeCarbon API capabilities to LLM clients through MCP tools and allow AI agents to run measurements locally thanks to CodeCarbon's library.

It is designed for a setup where the server runs with valid credentials and queries
experiment records directly from the official API.

## Features

- Read organizations, projects, and experiments from CodeCarbon API.
- Compute experiment consumption from run summaries.
- Recommend the least emitting experiment with an optional minimum accuracy.
- Create experiments from the agent.
- Measure energy locally, either around a manual start/stop, or by running a
  single command with `run_and_measure`.

## Requirements

- Python 3.12
- pip
- uv

## Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd codecarbon-mcp
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

The server will start and be ready to receive MCP client connections from an AI
agent such as Claude Code or Claude Desktop.

### Transport

The server speaks stdio by default, which is what an MCP host expects when it
launches the server as a subprocess. To serve over the network instead, set
`CODECARBON_MCP_TRANSPORT` to `sse` or `streamable-http`. Note that
`run_and_measure` is not available on those transports — see
[Security: shell execution](#security-shell-execution).

## Connect to an AI Agent

### What is MCP?

MCP (Model Context Protocol) allows AI assistants to communicate with external tools and data sources. This CodeCarbon server exposes its capabilities as MCP tools that AI agents can discover and use automatically.

### Connecting to Claude Code (CLI)

Claude Code is Anthropic's command-line interface that natively supports MCP servers.

1. **Add your MCP server**:

   From the repository root, run:
   ```bash
   claude mcp add codecarbon -- uv run server.py
   ```

2. **Verify the connection**:
   ```bash
   claude mcp list
   ```

   You should see:
   ```
   codecarbon: uv run server.py - ✓ Connected
   ```

3. **Restart Claude Code** to load the MCP server

4. **Start using it**:

   Once connected, you can interact naturally:
   ```
   "List my CodeCarbon organizations"
   "What's the consumption of my bert-base experiment?"
   "Which model consumes the least with 90% accuracy minimum?"
   "Measure how much energy 'python train.py' uses"
   ```

### Connecting to Claude Desktop (GUI)

For Claude Desktop on Mac/Windows:

1. Open the Claude Desktop configuration file:
   - **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
   - **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

2. Add the server configuration, replacing `cwd` with the path to your clone:
   ```json
   {
     "mcpServers": {
       "codecarbon": {
         "command": "uv",
         "args": ["run", "server.py"],
         "cwd": "/path/to/codecarbon-mcp"
       }
     }
   }
   ```

3. Restart Claude Desktop

### How It Works

```
┌─────────────────┐
│   AI Agent      │  (Claude Code / Claude Desktop)
│  (Claude LLM)   │
└────────┬────────┘
         │ JSON-RPC over STDIO
         ▼
┌─────────────────┐
│  MCP Server     │  (server.py)
│  FastMCP        │  Exposes the tools listed below
└────────┬────────┘
         │ HTTPS
         ▼
┌─────────────────┐
│ CodeCarbon API  │  (api.codecarbon.io)
└─────────────────┘
```

The AI agent:
1. **Discovers** available tools on startup
2. **Interprets** your natural language request
3. **Calls** the appropriate MCP tool(s)
4. **Formats** the response in a readable way

All communication happens automatically - you just ask questions in natural language!

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
- `create_experiment`

Local tools:
- `start_tracking`
- `stop_tracking`
- `get_status`
- `get_current_metrics`
- `run_and_measure` — local stdio servers only, see below

`get_current_metrics` returns elapsed time only. CodeCarbon does not expose
intermediate energy readings, so consumption figures are available only once
`stop_tracking` has finalised the session.

Local measurements cover the whole machine for the duration of the session, not
the measured process alone.

## Security: shell execution

⚠️ **`run_and_measure` executes an arbitrary shell command on the machine
running this server.**

The command string is passed to the system shell without sanitisation, so
anything that can call this tool has full control of the account the server runs
under — it can read your files, use your credentials, and reach anything on your
network. It is a remote code execution primitive by design, since measuring a
command's energy footprint means running it.

This is acceptable for a **local** server: the MCP host already runs on your
machine as you, so the tool grants no privilege the client did not already have.
It is **not** acceptable for a server reachable over a network, where it would
hand every client a shell on the host.

The server therefore enforces the following policy:

| Transport | `run_and_measure` |
| --- | --- |
| `stdio` (default, local) | Registered and callable |
| `sse`, `streamable-http` (networked) | Not registered, and refuses to run if called |

Two consequences worth knowing:

- On a networked transport the tool is not even advertised in `tools/list`, so
  the agent never sees it.
- Setting `CODECARBON_MCP_ALLOW_SHELL=0` disables the tool on a local server
  too. There is deliberately **no** value of that variable that re-enables it on
  a networked transport.

Remember that this only bounds *who* can ask for a command. Even locally, the
agent chooses what to run, so treat `run_and_measure` like handing your terminal
to the model: review what it proposes, and do not point it at untrusted input.
Commands are killed after 300 seconds.

## Accuracy Constraint Notes

The `recommend_lowest_emission_experiment` tool can enforce `min_accuracy`, but the API
does not expose a dedicated accuracy field today. The server infers accuracy from
experiment `name` or `description` when formatted like:

- `accuracy=92.4`
- `accuracy: 92.4%`

## Tests

```bash
uv run --extra dev pytest test_mcp.py -v
```

The suite starts the server over stdio, checks that the expected tools are
advertised and documented, and verifies the shell-execution policy above.
