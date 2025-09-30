
from typing import Optional

import json
import os
import urllib.parse

import requests  # type: ignore[import-untyped]


def download_report(
    sonarqube_host_url: str,
    sonarqube_token: str,
    sonarqube_org: str,
    sonarqube_project: str,
    branch: Optional[str],
    pull_request_id: Optional[str],
    report_path: str,
):
    print("DEBUG: Entering download_report function")
    headers = {"Authorization": f"Bearer {sonarqube_token}"}
    additional_search_params: dict[str, str] = {}

    if pull_request_id:
        additional_search_params["pullRequest"] = pull_request_id
        print(f"DEBUG: Using pull request mode with PR ID: {pull_request_id}")
    elif branch:
        additional_search_params["branch"] = branch
        print(f"DEBUG: Using branch mode with branch: {branch}")
    else:
        raise ValueError("Branch or pull request id is required")

    print(f"DEBUG: Search params: {additional_search_params}")

    print("DEBUG: Fetching issues...")
    issues = _get_all_pages(
        # https://sonarcloud.io/web_api/api/issues/search?deprecated=false
        f"{sonarqube_host_url}/api/issues/search?"
        + urllib.parse.urlencode(
            {
                "additionalFields": "_all",
                "organization": sonarqube_org,
                "projects": sonarqube_project,
                **additional_search_params,
            }
        ),
        headers,
        "issues",
        ["issues", "components", "rules"],
    )
    print(f"DEBUG: Found {len(issues.get('issues', []))} issues")

    print("DEBUG: Fetching hotspots...")
    hotspots = _get_all_pages(
        # https://sonarcloud.io/web_api/api/hotspots/search?deprecated=false
        f"{sonarqube_host_url}/api/hotspots/search?"
        + urllib.parse.urlencode(
            {
                "projectKey": sonarqube_project,
                **additional_search_params,
            }
        ),
        headers,
        "hotspots",
        ["hotspots", "components"],
    )
    print(f"DEBUG: Found {len(hotspots.get('hotspots', []))} hotspots")

    print("DEBUG: Fetching hotspot rules...")
    hotspot_rules = _get_all_pages(
        # https://sonarcloud.io/web_api/api/rules/search?deprecated=false
        f"{sonarqube_host_url}/api/rules/search?"
        + urllib.parse.urlencode(
            {
                "organization": sonarqube_org,
                "rule_keys": ",".join(
                    hotspot["ruleKey"] for hotspot in hotspots["hotspots"]
                ),
                "f": "name,lang,severity",
            }
        ),
        headers,
        "rules",
        ["rules"],
    )
    print(f"DEBUG: Found {len(hotspot_rules.get('rules', []))} rules")

    report = issues
    report["issues"] += hotspots["hotspots"]
    report["components"] += hotspots["components"]
    report["rules"] += hotspot_rules["rules"]

    print(f"DEBUG: Final report contains {len(report.get('issues', []))} total issues")
    print(f"DEBUG: Writing report to {report_path}")

    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
        
    print(f"DEBUG: Report written successfully to {report_path}")


def _get_all_pages(
    partial_url: str, headers: dict, stop_prop_name: str, merge_props: list[str]
) -> dict:
    result = {}
    page = 1

    while True:
        with requests.get(f"{partial_url}&p={page}&ps=500", headers=headers) as r:
            r.raise_for_status()
            page_data = r.json()

            if page == 1:
                result = page_data
            else:
                for merge_prop in merge_props:
                    result[merge_prop] += page_data[merge_prop]

            if len(page_data[stop_prop_name]) == 0:
                break

            page += 1

    return result


if __name__ == "__main__":
    print("DEBUG: Starting SonarQube report download...")
    
    # Get environment variables
    host_url = os.environ["SONARQUBE_HOST_URL"]
    token = os.environ["SONARQUBE_TOKEN"]
    org = os.environ["SONARQUBE_ORG"]
    project = os.environ["SONARQUBE_PROJECT"]
    branch = os.environ.get("BRANCH", "")
    pull_request_id = os.environ.get("PULL_REQUEST_ID", "")
    report_path = os.environ["REPORT_PATH"]
    
    print(f"DEBUG: host_url={host_url}")
    print(f"DEBUG: org={org}")
    print(f"DEBUG: project={project}")
    print(f"DEBUG: branch='{branch}'")
    print(f"DEBUG: pull_request_id='{pull_request_id}'")
    print(f"DEBUG: report_path={report_path}")
    
    # Convert empty strings to None for proper logic
    if branch == "":
        branch = None
    if pull_request_id == "":
        pull_request_id = None
        
    print(f"DEBUG: After conversion - branch={branch}, pull_request_id={pull_request_id}")
    
    try:
        download_report(host_url, token, org, project, branch, pull_request_id, report_path)
        print("DEBUG: Report download completed successfully!")
    except Exception as e:
        print(f"ERROR: Failed to download report: {e}")
        raise
