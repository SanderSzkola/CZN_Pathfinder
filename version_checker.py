from packaging.version import Version
from datetime import datetime, timedelta, timezone
import requests
from settings import Settings


def check_for_update(log):
    if not Settings.autoupdate:
        return

    now = datetime.now(timezone.utc)
    if (Settings.last_update_check is None or
            Settings.remote_version is None or
            now - Settings.last_update_check >= timedelta(days=2)):
        if Settings.testmode:
            log("Asking github for update")
        Settings.last_update_check = now
        url = "https://api.github.com/repos/SanderSzkola/CZN_Pathfinder/releases/latest"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        Settings.remote_version = response.json()["tag_name"]
        Settings.save()

    latest = Version(Settings.remote_version.lstrip("v"))
    current = Version(Settings.local_version.lstrip("v"))

    if latest > current:
        log(f"Update available: {latest} (current: {current})\n"
            f"https://github.com/SanderSzkola/CZN_Pathfinder/releases")
    else:
        if Settings.testmode:
            log(f"Version checker: GitHub version: {latest}; local: {current}")
