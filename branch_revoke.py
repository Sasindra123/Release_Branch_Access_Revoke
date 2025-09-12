import requests
import json
import argparse
import logging
from datetime import datetime

# Generate a timestamped filename for the log file
log_filename = datetime.now().strftime('access_revoke_%Y%m%d_%H%M%S.log')

# Configure logging
logging.basicConfig(
    filename=log_filename,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logging.getLogger().addHandler(console_handler)

# Load configuration from config
try:
    with open('config.json', 'r') as file:
        data = json.load(file)
    gitlab_api_url = data["gitlab_api_url"]
    repo_names = data["repo_names"]
    logging.info("Configuration loaded successfully.")
except Exception as e:
    logging.error(f"Failed to load configuration file: {e}")
    exit(1)

def get_project_id(repo_name, private_token):
    url = f"{gitlab_api_url}/projects?search={repo_name}"
    headers = {"PRIVATE-TOKEN": private_token}
    
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        projects = response.json()

        for project in projects:
            if project["name"] == repo_name:
                logging.info(f"Found project ID {project['id']} for repo '{repo_name}'")
                return project["id"]

        logging.warning(f"No matching project found for repo '{repo_name}'")
        return None

    except requests.exceptions.RequestException as e:
        logging.error(f"Error fetching project ID for repo '{repo_name}': {e}")
        return None
    except Exception as e:
        logging.error(f"Unexpected error while getting project ID for '{repo_name}': {e}")
        return None

# Branch Revoke Code 
def revoke_access(project_id, branch_name, private_token):
    full_branch_name = "release%2F" + branch_name
    url = f"{gitlab_api_url}/projects/{project_id}/protected_branches/{full_branch_name}"
    headers = {"PRIVATE-TOKEN": private_token}
    payload = {
        "allowed_to_push": [{"access_level": 40}],
        "allowed_to_merge": [{"access_level": 40}]
    }
    # allowed_to_push and merge are request keys, not repsonse keys and Gitlab Api follows some rules to set the access in protected branches.

    try:
        response = requests.patch(url, headers=headers, json=payload)
        if response.status_code == 200:
            logging.info(f"Successfully revoked access for branch '{branch_name}' in project ID {project_id}")
        else:
            logging.error(
                f"Failed to revoke access for branch '{branch_name}' in project ID {project_id}. "
                f"Status code: {response.status_code}, Response: {response.text}"
            )
    except requests.exceptions.RequestException as e:
        logging.error(f"Request error while revoking access for branch '{branch_name}': {e}")
    except Exception as e:
        logging.error(f"Unexpected error while revoking access for branch '{branch_name}': {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('-g','--gitlab_token',required=True)
    parser.add_argument('-b','--branches',nargs=3, type=str, required=True)
    args = parser.parse_args()
    private_token=args.gitlab_token

    logging.info(f"Branches list : {args.branches}")

    for repo_name in repo_names:
        logging.info(f"Processing repository...: {repo_name}")
        project_id = get_project_id(repo_name, private_token)

        if not project_id:
            logging.warning(f"Skipping repository '{repo_name}' due to missing project ID.")
            continue

        for branch_name in args.branches:
            logging.info(f"Revoking access for branch: {branch_name}")
            revoke_access(project_id, branch_name, private_token)
