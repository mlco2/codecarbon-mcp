from __future__ import annotations

from typing import Any

import requests


class CodeCarbonApiError(RuntimeError):
    """Raised when a CodeCarbon API request fails."""


class CodeCarbonApiClient:
    def __init__(
        self,
        base_url: str,
        api_token: str | None = None,
        access_token: str | None = None,
        timeout_seconds: int = 20,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_token = api_token
        self.access_token = access_token
        self.timeout_seconds = timeout_seconds

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_token:
            headers["x-api-token"] = self.api_token
        elif self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"
        return headers

    def _request(
        self, method: str, path: str, params: dict[str, Any] | None = None, json: dict[str, Any] | None = None
    ) -> Any:
        url = f"{self.base_url}{path}"
        response = requests.request(
            method=method,
            url=url,
            headers=self._headers(),
            params=params,
            json=json,
            timeout=self.timeout_seconds,
        )
        if response.status_code >= 400:
            raise CodeCarbonApiError(
                f"{method} {path} failed ({response.status_code}): {response.text}"
            )
        if response.content:
            return response.json()
        return None

    def check_auth(self) -> dict[str, Any]:
        return self._request("GET", "/auth/check")

    def list_organizations(self) -> list[dict[str, Any]]:
        return self._request("GET", "/organizations")

    def list_projects(self, organization_id: str) -> list[dict[str, Any]]:
        return self._request("GET", f"/organizations/{organization_id}/projects")

    def get_project(self, project_id: str) -> dict[str, Any]:
        return self._request("GET", f"/projects/{project_id}")

    def list_experiments(self, project_id: str) -> list[dict[str, Any]]:
        return self._request("GET", f"/projects/{project_id}/experiments")

    def get_experiment(self, experiment_id: str) -> dict[str, Any]:
        return self._request("GET", f"/experiments/{experiment_id}")

    def get_experiment_run_summaries(
        self,
        experiment_id: str,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[dict[str, Any]]:
        params = {}
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date
        return self._request(
            "GET", f"/experiments/{experiment_id}/runs/sums", params=params or None
        )

    def get_project_experiment_summaries(
        self,
        project_id: str,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[dict[str, Any]]:
        params = {}
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date
        return self._request(
            "GET", f"/projects/{project_id}/experiments/sums", params=params or None
        )

    def get_run(self, run_id: str) -> dict[str, Any]:
        return self._request("GET", f"/runs/{run_id}")

    def get_run_emissions(
        self,
        run_id: str,
        page: int = 1,
        page_size: int = 1000,
    ) -> dict[str, Any]:
        return self._request(
            "GET",
            f"/runs/{run_id}/emissions",
            params={"page": page, "size": page_size},
        )

    def create_experiment(
        self,
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
        """Create a new experiment."""
        payload = {
            "project_id": project_id,
            "name": name,
        }
        if description is not None:
            payload["description"] = description
        if timestamp is not None:
            payload["timestamp"] = timestamp
        if country_name is not None:
            payload["country_name"] = country_name
        if country_iso_code is not None:
            payload["country_iso_code"] = country_iso_code
        if region is not None:
            payload["region"] = region
        if on_cloud:
            payload["on_cloud"] = on_cloud
        if cloud_provider is not None:
            payload["cloud_provider"] = cloud_provider
        if cloud_region is not None:
            payload["cloud_region"] = cloud_region

        return self._request("POST", "/experiments", json=payload)