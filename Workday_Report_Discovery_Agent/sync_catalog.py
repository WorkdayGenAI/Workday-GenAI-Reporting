"""
sync_catalog.py — Sync report catalog from Workday RaaS URL.

Run with:  python sync_catalog.py
"""

import json
import logging
import os
import requests

import config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("sync_catalog")


def sync_from_workday(target_path: str = None) -> bool:
    """
    Fetch report catalog from Workday RaaS endpoint and save to target_path.
    """
    url = config.WORKDAY_RAAS_URL
    username = config.WORKDAY_ISU_USERNAME
    password = config.WORKDAY_ISU_PASSWORD
    output_path = target_path or config.DEFAULT_CATALOG_PATH

    if not url:
        logger.error("WORKDAY_RAAS_URL is not configured in environment variables or .env file.")
        return False
    if not username or not password:
        logger.error("WORKDAY_ISU_username or password is not configured.")
        return False

    logger.info("Starting sync from Workday RaaS URL: %s", url)
    logger.info("Using ISU Username: %s", username)

    try:
        # Request RaaS URL with Basic Authentication
        # The request gets formatted format=json as requested
        response = requests.get(
            url,
            auth=(username, password),
            headers={"Accept": "application/json"},
            timeout=120
        )
        
        if response.status_code != 200:
            logger.error(
                "Failed to fetch data from Workday. Status Code: %d, Response: %s",
                response.status_code,
                response.text[:200]
            )
            return False

        # Parse JSON to validate response format
        try:
            data = response.json()
        except ValueError as e:
            logger.error("Failed to parse response as JSON: %s", e)
            return False

        # Ensure directory exists and handle read-only filesystems (e.g., Vercel)
        try:
            os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=3, ensure_ascii=False)
        except OSError:
            logger.warning("Filesystem is read-only. Falling back to /tmp/workday_catalog.json")
            output_path = "/tmp/workday_catalog.json"
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=3, ensure_ascii=False)
            config.DEFAULT_CATALOG_PATH = output_path

        # Confirm length of reports
        num_reports = 0
        if isinstance(data, dict) and "Report_Entry" in data:
            num_reports = len(data["Report_Entry"])
        elif isinstance(data, list):
            num_reports = len(data)
        
        logger.info(
            "Successfully synced %d reports and saved to: %s",
            num_reports,
            output_path
        )
        return True

    except requests.exceptions.RequestException as e:
        logger.error("Network or request error occurred during sync: %s", e)
        return False
    except Exception as e:
        logger.error("An unexpected error occurred during sync: %s", e)
        return False


def main():
    logger.info("Executing catalog sync script...")
    success = sync_from_workday()
    if success:
        logger.info("Catalog sync completed successfully! ✅")
        exit(0)
    else:
        logger.error("Catalog sync failed. ❌")
        exit(1)


if __name__ == "__main__":
    main()
