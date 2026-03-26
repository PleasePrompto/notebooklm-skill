"""
Asana API client for NotebookLM Skill.

Usage:
    from asana_client import get_asana_client

    client = get_asana_client()
    me = client.users.get_user("me")
    print(f"Connected as: {me['name']} ({me['email']})")
"""

import os
import asana
from dotenv import load_dotenv

load_dotenv()


def get_asana_client() -> asana.Client:
    """Return an authenticated Asana client using ASANA_ACCESS_TOKEN."""
    token = os.getenv("ASANA_ACCESS_TOKEN")
    if not token:
        raise RuntimeError(
            "ASANA_ACCESS_TOKEN not set. "
            "Generate one at https://app.asana.com/0/developer-console "
            "and add it to your .env file."
        )
    client = asana.Client.access_token(token)
    client.headers = {"asana-enable": "new_memberships,new_goal_memberships"}
    return client
