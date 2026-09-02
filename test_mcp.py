#!/usr/bin/env python3
"""
Smoke tests for the MCP server.

Spawns server.py as a subprocess and drives it over stdio with raw JSON-RPC,
the same way an MCP host does. This exercises the real transport rather than
calling the tool functions directly.

Run with:
    uv run pytest test_mcp.py -v
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List

import pytest

SERVER = Path(__file__).parent / "server.py"

PROTOCOL_VERSION = "2024-11-05"

# Generous enough for CodeCarbon's hardware probing on a cold start.
READ_TIMEOUT_SECONDS = 60


class MCPSession:
    """A minimal JSON-RPC client speaking to server.py over stdio."""

    def __init__(self, env: Dict[str, str] | None = None):
        self._env = {**os.environ, **(env or {})}
        self._process: subprocess.Popen | None = None
        self._next_id = 0

    def __enter__(self) -> "MCPSession":
        self._process = subprocess.Popen(
            [sys.executable, str(SERVER)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            bufsize=1,
            env=self._env,
            cwd=str(SERVER.parent),
        )
        self._initialize()
        return self

    def __exit__(self, *exc_info) -> None:
        if self._process is None:
            return
        self._process.terminate()
        try:
            self._process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self._process.kill()

    def _send(self, payload: Dict[str, Any]) -> None:
        assert self._process is not None and self._process.stdin is not None
        self._process.stdin.write(json.dumps(payload) + "\n")
        self._process.stdin.flush()

    def _read_response(self) -> Dict[str, Any]:
        """Read the next JSON-RPC response, skipping blank lines."""
        assert self._process is not None and self._process.stdout is not None
        while True:
            line = self._process.stdout.readline()
            if not line:
                stderr = self._process.stderr.read() if self._process.stderr else ""
                raise AssertionError(f"Server closed the connection. stderr:\n{stderr}")
            if line.strip():
                return json.loads(line)

    def request(self, method: str, params: Dict[str, Any] | None = None) -> Dict[str, Any]:
        """Send a request and return its result, failing on a JSON-RPC error."""
        self._next_id += 1
        self._send({
            "jsonrpc": "2.0",
            "id": self._next_id,
            "method": method,
            "params": params or {},
        })
        response = self._read_response()
        assert "error" not in response, f"{method} failed: {response['error']}"
        return response["result"]

    def _initialize(self) -> None:
        result = self.request("initialize", {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": "test-client", "version": "1.0.0"},
        })
        assert "serverInfo" in result, f"Unexpected initialize result: {result}"
        # The handshake is only complete once the client acknowledges it.
        self._send({"jsonrpc": "2.0", "method": "notifications/initialized"})

    def list_tools(self) -> List[Dict[str, Any]]:
        return self.request("tools/list")["tools"]


@pytest.fixture(scope="module")
def local_tools() -> List[Dict[str, Any]]:
    """Tool list from a server started with the default (local, stdio) settings."""
    with MCPSession() as session:
        return session.list_tools()


def test_server_starts_and_lists_tools(local_tools):
    assert local_tools, "Server advertised no tools"


@pytest.mark.parametrize("name", [
    "start_tracking",
    "stop_tracking",
    "get_status",
    "get_current_metrics",
    "run_and_measure",
    "check_auth",
    "list_organizations",
    "list_projects",
    "list_experiments",
    "get_experiment_consumption",
    "get_experiment_consumption_by_name",
    "recommend_lowest_emission_experiment",
    "create_experiment",
    "demo_prompt_scenarios",
])
def test_expected_tool_is_advertised(local_tools, name):
    assert name in {tool["name"] for tool in local_tools}


def test_every_tool_is_documented(local_tools):
    undocumented = [t["name"] for t in local_tools if not t.get("description", "").strip()]
    assert not undocumented, f"Tools missing a description: {undocumented}"


def registered_tools(env: Dict[str, str]) -> set:
    """
    Tool names server.py registers under the given environment.

    A remote server cannot be driven over stdio, so the registration decision is
    inspected by importing the module in a subprocess rather than handshaking
    with it.
    """
    script = (
        "import asyncio, json, server; "
        "print(json.dumps([t.name for t in asyncio.run(server.mcp.list_tools())]))"
    )
    completed = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        env={**os.environ, **env},
        cwd=str(SERVER.parent),
        timeout=READ_TIMEOUT_SECONDS,
    )
    assert completed.returncode == 0, f"Import failed:\n{completed.stderr}"
    return set(json.loads(completed.stdout.strip().splitlines()[-1]))


@pytest.mark.parametrize("transport", ["sse", "streamable-http"])
def test_run_and_measure_is_hidden_on_a_remote_transport(transport):
    """A networked server must not advertise shell execution."""
    names = registered_tools({"CODECARBON_MCP_TRANSPORT": transport})

    assert "run_and_measure" not in names
    # The rest of the toolset must still be there.
    assert "start_tracking" in names
    assert "list_organizations" in names


def test_allow_shell_cannot_re_enable_a_remote_transport():
    """The override may only tighten the policy, never loosen it."""
    names = registered_tools({
        "CODECARBON_MCP_TRANSPORT": "sse",
        "CODECARBON_MCP_ALLOW_SHELL": "1",
    })

    assert "run_and_measure" not in names


def test_run_and_measure_can_be_disabled_locally():
    names = registered_tools({"CODECARBON_MCP_ALLOW_SHELL": "0"})

    assert "run_and_measure" not in names


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
