#!/usr/bin/env python3
"""
MCP Server for CodeCarbon.

This module exposes several MCP tools to start, stop, and monitor
energy consumption tracking via the CodeCarbon library, as well as
tools to interact with the CodeCarbon remote API (organizations,
projects, experiments, and recommendations).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime
import logging

from mcp.server.fastmcp import FastMCP
from codecarbon import EmissionsTracker
from analysis import aggregate_run_summaries, select_lowest_consumption_experiment
from client import CodeCarbonApiClient

# Initialize the MCP server
mcp = FastMCP("codecarbon")

# Global tracker for local energy tracking
tracker: Optional[EmissionsTracker] = None
start_time: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Local tracking tools
# ---------------------------------------------------------------------------

@mcp.tool()
async def start_tracking(measure_power_secs: int = 15) -> Dict[str, Any]:
    """
    Start energy tracking with CodeCarbon.

    Initializes a new EmissionsTracker session and begins monitoring
    power consumption. If a session is already active, returns an
    'already_running' status without starting a new one.

    Args:
        measure_power_secs: Interval in seconds between power measurements.
            Lower values give finer granularity but increase overhead.
            Defaults to 15.

    Returns:
        A dict with the following keys:
            - status (str): 'started' or 'already_running'.
            - start_time (str): ISO 8601 timestamp of when tracking began.
                Only present when status is 'started'.
            - project_name (str): Name of the CodeCarbon project.
                Only present when status is 'started'.
            - measurement_interval (int): The power measurement interval in seconds.
                Only present when status is 'started'.
    """
    global tracker, start_time

    if tracker is not None:
        return {
            "status": "already_running",
            "message": "Tracking is already in progress."
        }

    tracker = EmissionsTracker(
        project_name="mcp-codecarbon-tracking",
        measure_power_secs=measure_power_secs,
        log_level="info"
    )

    tracker.start()
    start_time = datetime.now()

    return {
        "status": "started",
        "start_time": start_time.isoformat(),
        "project_name": tracker._project_name,
        "measurement_interval": measure_power_secs
    }


@mcp.tool()
async def stop_tracking() -> Dict[str, Any]:
    """
    Stop the active energy tracking session and return final metrics.

    Finalizes the current EmissionsTracker session, computes total
    emissions, and clears the global tracker state.

    Returns:
        A dict with the following keys:
            - status (str): Always 'stopped'.
            - duration_seconds (float): Total elapsed time of the tracking
                session, rounded to 2 decimal places.
            - emissions_kg_co2 (float): Total CO2 equivalent emissions
                measured during the session, in kilograms.

    Raises:
        RuntimeError: If no tracking session is currently active.
    """
    global tracker, start_time

    if tracker is None:
        raise RuntimeError("No active tracking session.")

    emissions = tracker.stop()
    end_time = datetime.now()

    duration = (end_time - start_time).total_seconds() if start_time else 0

    tracker = None
    start_time = None

    return {
        "status": "stopped",
        "duration_seconds": round(duration, 2),
        "emissions_kg_co2": emissions
    }


@mcp.tool()
async def get_status() -> Dict[str, Any]:
    """
    Return the current state of the energy tracking session.

    Checks whether a tracking session is currently active without
    modifying any state.

    Returns:
        A dict with the following keys:
            - status (str): 'tracking' if a session is active,
                'not_tracking' otherwise.
            - start_time (str | None): ISO 8601 timestamp of when the active
                session started. Only present when status is 'tracking'.
    """
    if tracker is None:
        return {
            "status": "not_tracking"
        }

    return {
        "status": "tracking",
        "start_time": start_time.isoformat() if start_time else None
    }


@mcp.tool()
async def get_current_metrics() -> Dict[str, Any]:
    """
    Return timing information about the ongoing tracking session.

    Provides a snapshot of elapsed time without stopping the tracker.
    Useful for monitoring long-running sessions.

    Returns:
        A dict with the following keys:
            - status (str): Always 'tracking'.
            - start_time (str): ISO 8601 timestamp of when the session began.
            - current_time (str): ISO 8601 timestamp of the current moment.
            - duration_seconds (float): Elapsed time since tracking started,
                rounded to 2 decimal places.

    Raises:
        RuntimeError: If no tracking session is currently active.
    """
    if tracker is None or start_time is None:
        raise RuntimeError("No active tracking session.")

    now = datetime.now()
    duration = (now - start_time).total_seconds()

    return {
        "status": "tracking",
        "start_time": start_time.isoformat(),
        "current_time": now.isoformat(),
        "duration_seconds": round(duration, 2)
    }


# ---------------------------------------------------------------------------
# CodeCarbon API tools (remote)
# ---------------------------------------------------------------------------

def _get_access_token_from_file() -> str:
    """
    Read the CodeCarbon API access token from a local credentials file.

    Looks for a 'credentials.json' file in the current working directory,
    which is typically created by running `codecarbon login`. Parses the
    file and extracts the access token from the nested token structure.

    Returns:
        The access token string to be used for API authentication.

    Raises:
        FileNotFoundError: If 'credentials.json' does not exist in the
            current working directory.
        ValueError: If the credentials file exists but does not contain
            a valid 'access_token' field.
    """
    cred_path = Path("credentials.json")
    if not cred_path.exists():
        raise FileNotFoundError(
            f"No credentials file found at {cred_path}. Please run `codecarbon login` first."
        )
    with cred_path.open("r") as f:
        data = json.load(f)
    try:
        return data["tokens"]["access_token"]
    except KeyError:
        raise ValueError(
            "No access_token found in credentials file. Run `codecarbon login` again."
        )


def _build_client() -> CodeCarbonApiClient:
    """
    Build and return an authenticated CodeCarbon API client.

    Reads credentials from the local credentials file and instantiates
    a CodeCarbonApiClient pointed at the production API endpoint.

    Returns:
        A configured CodeCarbonApiClient instance ready to make
        authenticated requests.

    Raises:
        FileNotFoundError: If the credentials file is missing.
        ValueError: If the credentials file lacks a valid access token.
    """
    base_url = "https://api.codecarbon.io"
    access_token = _get_access_token_from_file()
    return CodeCarbonApiClient(base_url=base_url, access_token=access_token)


@mcp.tool()
def check_auth() -> dict[str, Any]:
    """
    Validate that the configured credentials can access the CodeCarbon API.

    Performs a lightweight authenticated request to verify that the stored
    access token is valid and has not expired.

    Returns:
        A dict confirming authentication status, as returned by the API.

    Raises:
        FileNotFoundError: If the credentials file is missing.
        ValueError: If the credentials file lacks a valid access token.
    """
    return _build_client().check_auth()


@mcp.tool()
def list_organizations() -> list[dict[str, Any]]:
    """
    List all organizations visible to the configured credentials.

    Returns:
        A list of organization dicts, each typically containing:
            - id (str): Unique identifier of the organization.
            - name (str): Display name of the organization.

    Raises:
        FileNotFoundError: If the credentials file is missing.
        ValueError: If the credentials file lacks a valid access token.
    """
    return _build_client().list_organizations()


@mcp.tool()
def list_projects(organization_id: str) -> list[dict[str, Any]]:
    """
    List all projects under a given organization.

    Args:
        organization_id: The unique identifier of the organization whose
            projects should be retrieved.

    Returns:
        A list of project dicts, each typically containing:
            - id (str): Unique identifier of the project.
            - name (str): Display name of the project.
            - description (str | None): Optional project description.

    Raises:
        FileNotFoundError: If the credentials file is missing.
        ValueError: If the credentials file lacks a valid access token.
    """
    return _build_client().list_projects(organization_id)


@mcp.tool()
def list_experiments(project_id: str) -> list[dict[str, Any]]:
    """
    List all experiments under a given project.

    Args:
        project_id: The unique identifier of the project whose
            experiments should be retrieved.

    Returns:
        A list of experiment dicts, each typically containing:
            - id (str): Unique identifier of the experiment.
            - name (str): Display name of the experiment.
            - description (str | None): Optional experiment description.
            - project_id (str): The parent project identifier.

    Raises:
        FileNotFoundError: If the credentials file is missing.
        ValueError: If the credentials file lacks a valid access token.
    """
    return _build_client().list_experiments(project_id)


@mcp.tool()
def get_experiment_consumption(
    experiment_id: str,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, Any]:
    """
    Return aggregated energy consumption for a specific experiment.

    Fetches all runs for the given experiment and aggregates their
    consumption metrics. Optionally restricts the aggregation to runs
    that fall within a specified date window.

    Args:
        experiment_id: The unique identifier of the experiment to query.
        start_date: Optional ISO 8601 date string (e.g. '2024-01-01').
            Only runs on or after this date are included.
        end_date: Optional ISO 8601 date string (e.g. '2024-12-31').
            Only runs on or before this date are included.

    Returns:
        A dict with the following keys:
            - experiment (dict): Metadata about the experiment, including
                id, name, description, and project_id.
            - window (dict): The applied date filters with keys
                'start_date' and 'end_date'.
            - totals (dict): Aggregated consumption metrics across all
                matching runs (e.g. total energy in kWh, total CO2 in kg).
            - runs (list[dict]): Individual run summaries used
                for the aggregation.

    Raises:
        FileNotFoundError: If the credentials file is missing.
        ValueError: If the credentials file lacks a valid access token.
    """
    client = _build_client()
    experiment = client.get_experiment(experiment_id)
    run_summaries = client.get_experiment_run_summaries(
        experiment_id=experiment_id,
        start_date=start_date,
        end_date=end_date,
    )
    totals = aggregate_run_summaries(run_summaries)
    return {
        "experiment": {
            "id": experiment.get("id"),
            "name": experiment.get("name"),
            "description": experiment.get("description"),
            "project_id": experiment.get("project_id"),
        },
        "window": {"start_date": start_date, "end_date": end_date},
        "totals": totals,
        "runs": run_summaries,
    }


@mcp.tool()
def get_experiment_consumption_by_name(
    project_id: str,
    experiment_name: str,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, Any]:
    """
    Find an experiment by name in a project and return its consumption.

    Performs an exact name match first, then falls back to a case-insensitive
    partial match. If multiple experiments match, returns a disambiguation
    message instead of consumption data.

    Args:
        project_id: The unique identifier of the project to search within.
        experiment_name: The experiment name to search for. Matching is
            case-insensitive; partial matches are used if no exact match
            is found.
        start_date: Optional ISO 8601 date string. Only runs on or after
            this date are included in the consumption totals.
        end_date: Optional ISO 8601 date string. Only runs on or before
            this date are included in the consumption totals.

    Returns:
        If exactly one experiment matches: the full consumption dict as
        returned by get_experiment_consumption().
        If no experiments match: a dict with keys 'message' (str) and
        'matches' (empty list).
        If multiple experiments match: a dict with keys 'message' (str)
        and 'matches' (list of dicts with 'id' and 'name').

    Raises:
        FileNotFoundError: If the credentials file is missing.
        ValueError: If the credentials file lacks a valid access token.
    """
    client = _build_client()
    experiments = client.list_experiments(project_id)
    lowered = experiment_name.strip().lower()
    exact = [exp for exp in experiments if exp.get("name", "").strip().lower() == lowered]
    partial = [exp for exp in experiments if lowered in exp.get("name", "").strip().lower()]
    matches = exact or partial
    if not matches:
        return {
            "message": f"No experiment found for name '{experiment_name}' in project {project_id}.",
            "matches": [],
        }
    if len(matches) > 1:
        return {
            "message": f"Multiple experiments match '{experiment_name}'.",
            "matches": [{"id": m.get("id"), "name": m.get("name")} for m in matches],
        }
    return get_experiment_consumption(
        experiment_id=matches[0]["id"], start_date=start_date, end_date=end_date
    )


@mcp.tool()
def recommend_lowest_emission_experiment(
    project_id: str,
    min_accuracy: float | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, Any]:
    """
    Recommend the least carbon-emitting experiment in a project.

    Fetches all experiment summaries for the project and selects the one
    with the lowest total CO2 emissions. Optionally filters candidates by
    a minimum accuracy threshold, which is inferred from experiment names
    or descriptions formatted as 'accuracy=92.1' or 'accuracy: 92.1%'.

    Args:
        project_id: The unique identifier of the project to evaluate.
        min_accuracy: Optional minimum accuracy percentage (e.g. 92.0).
            Experiments whose inferred accuracy falls below this threshold
            are excluded from consideration.
        start_date: Optional ISO 8601 date string. Only runs on or after
            this date are included when computing experiment totals.
        end_date: Optional ISO 8601 date string. Only runs on or before
            this date are included when computing experiment totals.

    Returns:
        A dict with the following keys:
            - project_id (str): The queried project identifier.
            - window (dict): The applied date filters with keys
                'start_date' and 'end_date'.
            - recommendation (dict | None): The recommended experiment with
                the lowest emissions, or None if no experiment meets the
                criteria.
            - experiments_considered (int): Total number of experiments
                evaluated before applying accuracy filtering.

    Raises:
        FileNotFoundError: If the credentials file is missing.
        ValueError: If the credentials file lacks a valid access token.
    """
    client = _build_client()
    reports = client.get_project_experiment_summaries(
        project_id=project_id, start_date=start_date, end_date=end_date
    )
    recommendation = select_lowest_consumption_experiment(
        experiment_reports=reports,
        min_accuracy=min_accuracy,
    )
    return {
        "project_id": project_id,
        "window": {"start_date": start_date, "end_date": end_date},
        "recommendation": recommendation,
        "experiments_considered": len(reports),
    }


@mcp.tool()
def create_experiment(
    project_id: str,
    name: str,
    description: str | None = None,
    timestamp: str | None = None,
    country_name: str | None = None,
    country_iso_code: str | None = None,
    region: str | None = None,
    on_cloud: bool = False,
    cloud_provider: str | None = None,
    cloud_region: str | None = None,
) -> dict[str, Any]:
    """
    Create a new experiment in a CodeCarbon project.

    Registers a new experiment under the specified project with optional
    metadata describing the hardware environment and geographic location.
    Cloud-related fields are only relevant when on_cloud is True.

    Args:
        project_id: The unique identifier of the project to create the
            experiment in.
        name: Display name for the new experiment.
        description: Optional free-text description. Can include structured
            metadata such as 'accuracy=92.1' for use with the recommendation
            tool.
        timestamp: Optional ISO 8601 timestamp to associate with the
            experiment creation. Defaults to the current time if omitted.
        country_name: Optional full name of the country where the experiment
            runs (e.g. 'France').
        country_iso_code: Optional ISO 3166-1 alpha-3 country code
            (e.g. 'FRA').
        region: Optional geographic region or data center location within
            the country (e.g. 'eu-west-3').
        on_cloud: Whether the experiment runs on cloud infrastructure.
            Defaults to False.
        cloud_provider: Optional cloud provider name (e.g. 'aws', 'gcp',
            'azure'). Only relevant when on_cloud is True.
        cloud_region: Optional cloud region identifier (e.g. 'us-east-1').
            Only relevant when on_cloud is True.

    Returns:
        A dict representing the newly created experiment as returned by
        the CodeCarbon API, typically including the assigned 'id' and
        all provided metadata fields.

    Raises:
        FileNotFoundError: If the credentials file is missing.
        ValueError: If the credentials file lacks a valid access token.
    """
    client = _build_client()
    return client.create_experiment(
        project_id=project_id,
        name=name,
        description=description,
        timestamp=timestamp,
        country_name=country_name,
        country_iso_code=country_iso_code,
        region=region,
        on_cloud=on_cloud,
        cloud_provider=cloud_provider,
        cloud_region=cloud_region,
    )


@mcp.tool()
def demo_prompt_scenarios() -> list[dict[str, str]]:
    """
    Return a list of example prompts to demonstrate the MCP server's capabilities.

    Each scenario illustrates a typical use case paired with the primary
    tool it exercises. Intended for onboarding, testing, and showcasing
    available functionality to new users.

    Returns:
        A list of scenario dicts, each containing:
            - title (str): Short label for the scenario.
            - prompt (str): A natural-language prompt a user might send.
            - tool_chain (str): The primary MCP tool invoked by the prompt.
    """
    return [
        {
            "title": "Experiment Consumption - Desktop Ben",
            "prompt": "What is the consumption of my experiment 'Desktop Ben' (GTX 1080 ti)?",
            "tool_chain": "get_experiment_consumption_by_name",
        },
        {
            "title": "Experiment Consumption - Laptop",
            "prompt": "What is the consumption of my experiment 'Laptop' (Laptop with RAPL Intel(R) Core(TM) Ultra 7 265H)?",
            "tool_chain": "get_experiment_consumption_by_name",
        },
        {
            "title": "Comparison with Accuracy Constraint",
            "prompt": "Which model consumes the least with a minimum accuracy of 92%?",
            "tool_chain": "recommend_lowest_emission_experiment(min_accuracy=92)",
        },
        {
            "title": "Project Inventory",
            "prompt": "List the available experiments in my project.",
            "tool_chain": "list_experiments",
        },
        {
            "title": "Create a Simple Experiment",
            "prompt": "Create a new experiment named 'test experiment' in my project",
            "tool_chain": "create_experiment",
        },
    ]


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    """
    Start the MCP server in stdio mode.

    Configures logging and launches the FastMCP server using standard
    input/output as the communication transport. This is the expected
    entry point when the server is invoked as a subprocess by an MCP host.
    """
    logging.info("Starting MCP server...")
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()