#!/usr/bin/env python3
"""
CodeCarbon tracking session management.

Wraps the lifecycle of a single :class:`codecarbon.EmissionsTracker` behind a
small class, so the MCP tools in ``server.py`` do not have to juggle
module-level mutable state.
"""

from __future__ import annotations

import logging
import subprocess
from datetime import datetime
from typing import Any, Dict, Optional

from codecarbon import EmissionsTracker

logger = logging.getLogger(__name__)

# Wall-clock budget granted to a command run by run_and_measure.
COMMAND_TIMEOUT_SECONDS = 300

# Trailing characters of stdout/stderr echoed back to the caller. The output of
# a measured command can be arbitrarily large; only the tail is useful context.
OUTPUT_TAIL_CHARS = 2000

DEFAULT_PROJECT_NAME = "mcp-codecarbon-tracking"


class CodeCarbonTracker:
    """Manage the lifecycle of a single CodeCarbon tracking session."""

    def __init__(self, project_name: str = DEFAULT_PROJECT_NAME) -> None:
        self.project_name = project_name
        self._tracker: Optional[EmissionsTracker] = None
        self._start_time: Optional[datetime] = None

    @property
    def is_tracking(self) -> bool:
        """Whether a tracking session is currently active."""
        return self._tracker is not None

    def start(
        self,
        measure_power_secs: int = 15,
        save_to_file: bool = True,
        restart: bool = False,
    ) -> Dict[str, Any]:
        """
        Begin a tracking session.

        Args:
            measure_power_secs: Interval in seconds between power measurements.
            save_to_file: Whether CodeCarbon should also append the results to
                its CSV output file.
            restart: If a session is already active, stop it and start a fresh
                one instead of reporting 'already_running'.

        Returns:
            A dict with the following keys:
                - status (str): 'started' or 'already_running'.
                - start_time (str): ISO 8601 timestamp of when tracking began.
                    Only present when status is 'started'.
                - project_name (str): Name of the CodeCarbon project.
                    Only present when status is 'started'.
                - measurement_interval (int): The power measurement interval in
                    seconds. Only present when status is 'started'.
        """
        if self.is_tracking:
            if not restart:
                return {
                    "status": "already_running",
                    "message": "Tracking is already in progress."
                }
            self.stop()

        self._tracker = EmissionsTracker(
            project_name=self.project_name,
            measure_power_secs=measure_power_secs,
            save_to_file=save_to_file,
            log_level="info"
        )
        self._tracker.start()
        self._start_time = datetime.now()

        return {
            "status": "started",
            "start_time": self._start_time.isoformat(),
            "project_name": self.project_name,
            "measurement_interval": measure_power_secs
        }

    def stop(self) -> Dict[str, Any]:
        """
        Stop the active session and return its final metrics.

        Returns:
            A dict with the following keys:
                - status (str): Always 'stopped'.
                - duration_seconds (float): Total elapsed time of the tracking
                    session, rounded to 2 decimal places.
                - emissions_kg_co2 (float): Total CO2 equivalent emissions
                    measured during the session, in kilograms.
                - energy_consumed_kwh, cpu_energy_kwh, gpu_energy_kwh,
                    ram_energy_kwh (float | None): Energy breakdown reported by
                    CodeCarbon, in kilowatt-hours.
                - country_name, country_iso_code (str | None): Location used to
                    convert energy into emissions.

        Raises:
            RuntimeError: If no tracking session is currently active.
        """
        if not self.is_tracking:
            raise RuntimeError("No active tracking session.")

        emissions = self._tracker.stop()
        data = self._tracker.final_emissions_data
        end_time = datetime.now()

        duration = (end_time - self._start_time).total_seconds() if self._start_time else 0

        result = {
            "status": "stopped",
            "duration_seconds": round(duration, 2),
            "emissions_kg_co2": emissions
        }

        # final_emissions_data is None when CodeCarbon could not complete a
        # measurement (very short sessions, unsupported hardware).
        if data is not None:
            result.update({
                "energy_consumed_kwh": data.energy_consumed,
                "cpu_energy_kwh": data.cpu_energy,
                "gpu_energy_kwh": data.gpu_energy,
                "ram_energy_kwh": data.ram_energy,
                "country_name": data.country_name,
                "country_iso_code": data.country_iso_code
            })

        self._reset()
        return result

    def status(self) -> Dict[str, Any]:
        """
        Report whether a session is active, without modifying any state.

        Returns:
            A dict with the following keys:
                - status (str): 'tracking' or 'not_tracking'.
                - start_time (str | None): ISO 8601 timestamp of when the active
                    session started. Only present when status is 'tracking'.
        """
        if not self.is_tracking:
            return {
                "status": "not_tracking"
            }

        return {
            "status": "tracking",
            "start_time": self._start_time.isoformat() if self._start_time else None
        }

    def elapsed(self) -> Dict[str, Any]:
        """
        Report timing information about the ongoing session.

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
        if not self.is_tracking or self._start_time is None:
            raise RuntimeError("No active tracking session.")

        now = datetime.now()

        return {
            "status": "tracking",
            "start_time": self._start_time.isoformat(),
            "current_time": now.isoformat(),
            "duration_seconds": round((now - self._start_time).total_seconds(), 2)
        }

    def run_and_measure(
        self,
        command: str,
        measure_power_secs: int = 15,
        save_to_file: bool = False,
        timeout_seconds: int = COMMAND_TIMEOUT_SECONDS,
    ) -> Dict[str, Any]:
        """
        Run a shell command and measure the energy it consumes.

        Brackets the command with a tracking session, so the returned metrics
        cover the machine for the duration of the command.

        SECURITY: ``command`` is executed through the system shell with no
        sanitisation, so this grants whoever calls it full control of the host
        account. It is only safe when the caller already has shell access to
        this machine. ``server.py`` gates the corresponding MCP tool on a local
        stdio transport; do not call this method directly from a networked
        entry point.

        Args:
            command: Shell command to execute (e.g. 'python3 my_script.py').
            measure_power_secs: Interval in seconds between power measurements.
            save_to_file: Whether CodeCarbon should also append the results to
                its CSV output file.
            timeout_seconds: Wall-clock budget for the command.

        Returns:
            The dict returned by :meth:`stop`, plus:
                - command (str): The command that was executed.
                - returncode (int): Exit status of the command.
                - stdout (str): Tail of the command's standard output.
                - stderr (str): Tail of the command's standard error.

        Raises:
            RuntimeError: If the command could not be run to completion, or if
                the tracking session failed to finalise.
        """
        self.start(
            measure_power_secs=measure_power_secs,
            save_to_file=save_to_file,
            restart=True
        )

        try:
            process = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout_seconds
            )
            metrics = self.stop()
        except Exception as exc:
            self._abort()
            raise RuntimeError(f"Failed to run and measure command: {exc}") from exc

        metrics["command"] = command
        metrics["returncode"] = process.returncode
        metrics["stdout"] = (process.stdout or "")[-OUTPUT_TAIL_CHARS:]
        metrics["stderr"] = (process.stderr or "")[-OUTPUT_TAIL_CHARS:]
        return metrics

    def _abort(self) -> None:
        """Tear down a session after a failure, ignoring CodeCarbon errors."""
        if self._tracker is not None:
            try:
                self._tracker.stop()
            except Exception:
                logger.warning("Failed to stop the tracker while aborting.", exc_info=True)
        self._reset()

    def _reset(self) -> None:
        """Clear all session state."""
        self._tracker = None
        self._start_time = None
