"""
This script is a demo on how to login to the API.
It read the credentials in .codecarbon.config or $HOME/.codecarbon.config
Then it call /organizations/{organization_id}/sums to get the emmissions.

Use it with:
    uv run codecarbon login
    uv run example/api_login.py
"""
import os
import sys
from pathlib import Path
import configparser
from typing import Optional

import requests
from fief_client import Fief
from fief_client.integrations.cli import FiefAuth
from rich import print

# Authentication configuration
AUTH_CLIENT_ID = os.environ.get(
    "AUTH_CLIENT_ID",
    "jsUPWIcUECQFE_ouanUuVhXx52TTjEVcVNNtNGeyAtU",
)
AUTH_SERVER_URL = os.environ.get(
    "AUTH_SERVER_URL", "https://auth.codecarbon.io/codecarbon"
)
API_URL = os.environ.get("API_URL", "https://dashboard.codecarbon.io/api")


def get_config(path: Optional[Path] = None):
    """Read configuration from .codecarbon.config file."""
    # Try current directory first
    p = path or Path.cwd().resolve() / ".codecarbon.config"
    
    if p.exists():
        config = configparser.ConfigParser()
        config.read(str(p))
        if "codecarbon" in config.sections():
            return dict(config["codecarbon"])
    
    # Try home directory
    home_config = Path.home() / ".codecarbon.config"
    if home_config.exists():
        config = configparser.ConfigParser()
        config.read(str(home_config))
        if "codecarbon" in config.sections():
            return dict(config["codecarbon"])
    
    raise FileNotFoundError(
        "No .codecarbon.config file found in current directory or home directory."
    )


def get_api_endpoint(path: Optional[Path] = None):
    """Get API endpoint from config file."""
    p = path or Path.cwd().resolve() / ".codecarbon.config"
    
    if p.exists():
        config = configparser.ConfigParser()
        config.read(str(p))
        if "codecarbon" in config.sections():
            d = dict(config["codecarbon"])
            if "api_endpoint" in d:
                return d["api_endpoint"]
    
    # Try home directory
    home_config = Path.home() / ".codecarbon.config"
    if home_config.exists():
        config = configparser.ConfigParser()
        config.read(str(home_config))
        if "codecarbon" in config.sections():
            d = dict(config["codecarbon"])
            if "api_endpoint" in d:
                return d["api_endpoint"]
    
    return "https://api.codecarbon.io"


def get_fief_auth():
    """Create Fief authentication client."""
    fief = Fief(AUTH_SERVER_URL, AUTH_CLIENT_ID)
    fief_auth = FiefAuth(fief, "./credentials.json")
    return fief_auth


def get_access_token():
    """Retrieve access token for API authentication."""
    try:
        access_token_info = get_fief_auth().access_token_info()
        access_token = access_token_info["access_token"]
        return access_token
    except Exception as e:
        raise ValueError(
            f"Not able to retrieve the access token, please run `codecarbon login` first! (error: {e})"
        )


def main():
    """Main function to login and retrieve emissions data."""
    print("[bold blue]CodeCarbon API Login Demo[/bold blue]\n")
    
    try:
        # Read configuration
        print("Reading configuration...")
        config = get_config()
        print(f"✓ Configuration loaded")
        
        # Get API endpoint
        api_endpoint = get_api_endpoint()
        print(f"✓ API endpoint: {api_endpoint}")
        
        # Get organization ID from config
        if "organization_id" not in config:
            print("[bold red]Error:[/bold red] No organization_id found in config file")
            sys.exit(1)
        
        organization_id = config["organization_id"]
        print(f"✓ Organization ID: {organization_id}")
        
        # Authenticate and get access token
        print("\nAuthenticating...")
        access_token = get_access_token()
        print("✓ Authentication successful")
        
        # Call API to get emissions sums
        print(f"\nFetching emissions data for organization {organization_id}...")
        url = f"{api_endpoint}/organizations/{organization_id}/sums"
        headers = {"Authorization": f"Bearer {access_token}"}
        
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        
        emissions_data = response.json()
        
        # Display results
        print("\n[bold green]Emissions Data:[/bold green]")
        print(emissions_data)
        
    except FileNotFoundError as e:
        print(f"[bold red]Error:[/bold red] {e}")
        print("\nPlease create a .codecarbon.config file or run 'codecarbon config' first.")
        sys.exit(1)
    except ValueError as e:
        print(f"[bold red]Error:[/bold red] {e}")
        sys.exit(1)
    except requests.exceptions.RequestException as e:
        print(f"[bold red]API Error:[/bold red] {e}")
        sys.exit(1)
    except Exception as e:
        print(f"[bold red]Unexpected Error:[/bold red] {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
