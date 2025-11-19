import requests
import json
import re
import argparse
import logging
from itertools import islice
from datetime import datetime
import config

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

gitlab_api_url = config.gitlab_api_url
jira_api_url = config.jira_api_url
# project_search = config.project_search
project_search_all = config.project_search_all
# target_branch = config.target_branch
username = config.username
password = config.password


def get_username(jira_id):
    """Retrieves the assignee's display name from a Jira ticket."""
    url = f"{jira_api_url}/issue/{jira_id}"
    logging.info(f"Attempting to retrieve Jira issue details for: {jira_id}")
    try:
        response = requests.get(url, auth=(username, password))
        
        if response.status_code == 200:
            logging.info(f"Successfully retrieved Jira details for {jira_id}. Status Code: 200")
            userresponse_json = response.json()
            
            # Check if the returned key matches the requested Jira ID
            if userresponse_json['key'] != jira_id:
                error_message = f"Mismatched Jira ID. Requested: {jira_id}, Received: {userresponse_json['key']}. Status Code: {response.status_code}"
                logging.error(error_message)
                return "error", error_message
                
            assignee = userresponse_json["fields"]["assignee"]["displayName"]
            logging.info(f"Assignee found for {jira_id}: {assignee}")
            print("get_username", assignee)
            return "Success", assignee
        else:
            error_message = f"Failed to retrieve Jira details for {jira_id}. Status Code: {response.status_code}. Response: {response.text}"
            logging.error(error_message)
            return "error", error_message
            
    except requests.exceptions.RequestException as e:
        error_message = f"Request error while fetching Jira details for {jira_id}: {e}"
        logging.error(error_message)
        return "error", error_message

def get_branch_project_map(jira_id, private_token, qa_mode=False):
    # Retrieves Gitlab projects and release branches associated with a Jira ID via MR search.
    print("branch_project_map executing...")
    api_url = f"{gitlab_api_url}{project_search_all}{jira_id}"
    logging.info(f"Searching GitLab Merge Requests for Jira ID: {jira_id} at {api_url}")
    
    projectId_branch_map = {} 
    projectId_repo_map = {} # This seems unused except for the fallback logic

    try:
        mr_response = requests.get(api_url, headers={"PRIVATE-TOKEN": private_token})
        
        if mr_response.status_code != 200:
            error_message = f"GitLab API request failed for {jira_id}. Status Code: {mr_response.status_code}. Response: {mr_response.text}"
            logging.error(error_message)
            
            # Fallback logic for DEV tickets with no MRs
            if (not projectId_repo_map) and (jira_id.split('-')[0] == 'DEV') and (not qa_mode):
                projectId_repo_map.update(config.default_repo)
                limited_repos = dict(islice(projectId_repo_map.items(), 5))
                logging.warning(f"No MRs found for DEV ticket {jira_id}. Falling back to default repositories: {list(limited_repos.keys())}")
                return "Success", {} 
            else:
                return "error", error_message
        
        response_data = mr_response.json()
        logging.info(f"Successfully retrieved {len(response_data)} merge requests for {jira_id}.")
        
        for item in response_data:
            project_id = item.get('target_project_id')
            target_branch_full = item.get('target_branch')
            print(item.get('web_url'))
            logging.info(f"web url : {item.get('web_url')}")
            if project_id and target_branch_full:
                if target_branch_full.startswith("release/"):
                    branch_name = target_branch_full.split('/', 1)[1]
                    logging.debug(f"Found release branch '{target_branch_full}' in project {project_id}.")
                else:
                    logging.debug(f"Skipping non-release branch: {target_branch_full} in project {project_id}")
                    continue

                if project_id not in projectId_branch_map:
                    projectId_branch_map[project_id] = []
                
                if branch_name not in projectId_branch_map[project_id]:
                    projectId_branch_map[project_id].append(branch_name)

        if not projectId_branch_map:
             error_message = f"No release branches found for Jira {jira_id} in any merge request."
             logging.warning(error_message)
             return "error", error_message
             
        if len(projectId_branch_map) > 5:
            warning_message = f"There are more than five repos associated with {jira_id} ({len(projectId_branch_map)}). Limiting to the first 5 repos."
            logging.warning(warning_message)
            
        limited_map = dict(islice(projectId_branch_map.items(), 5))
        logging.info(f"Project-Branch map finalized for {jira_id}: {limited_map}")
        return "Success", limited_map

    except requests.exceptions.RequestException as e:
        error_message = f"Request error while fetching GitLab MRs for {jira_id}: {e}"
        logging.error(error_message)
        return "error", error_message
    except Exception as e:
        error_message = f"Unexpected error in get_branch_project_map for {jira_id}: {e}"
        logging.error(error_message)
        return "error", error_message
    
    
# filter_id based
def get_jirafilterlist(filterid):
    filterstring = f"{jira_api_url}/search?jql=filter={filterid}&fields=key"
    logging.info(f"Fetching Jira list from filter ID: {filterid}")
    try:
        response = requests.get(filterstring, auth=(username, password))
        if response.status_code == 200:
            filterresponse_json = response.json()
            jiraslist = [item['key'] for item in filterresponse_json.get('issues', [])]
            logging.info(f"Successfully retrieved {len(jiraslist)} Jiras from filter {filterid}. Status Code: 200")
            return jiraslist
        else:
            logging.error(f"Failed to retrieve Jira list from filter {filterid}. Status Code: {response.status_code}. Response: {response.text}")
            return "error"
    except requests.exceptions.RequestException as e:
        logging.error(f"Request error while fetching Jira filter {filterid}: {e}")
        return "error"
    

# Revoke Script
def revoke_access(username, branch_project_id_map, private_token):
    """Revokes push/merge access for a user on protected GitLab branches."""
    logging.info(f"--- Starting access revocation for user '{username}' ---")
    print("---------------Fetching details for revoke---------------------")
    print("User to revoke", username)
    print("Branch and project map details", branch_project_id_map)

    for project_id, branches in branch_project_id_map.items():
        logging.info(f"Processing Project ID: {project_id}")
        print(f"Processing Project ID: {project_id}")
        for branch in branches:
            full_branch_name = f"release%2F{branch}"
            logging.info(f"Checking protected branch: {full_branch_name}")
            print(f"Processing branch: {full_branch_name}")

            base_url = f"{gitlab_api_url}/projects/{project_id}/protected_branches/{full_branch_name}"
            headers = {
                "PRIVATE-TOKEN": private_token,
                "Content-Type": "application/json"
            }

            push_access_rule_id = None
            merge_access_rule_id = None
            
            try:
                response = requests.get(base_url, headers=headers) 
                if response.status_code == 404:
                    logging.warning(f"Branch 'release/{branch}' is not protected in project ID {project_id} (404 Not Found). Skipping revocation.")
                    continue
                    
                response.raise_for_status() 
                response_data = response.json()
                logging.info(f"Successfully retrieved protected branch details for 'release/{branch}' (Status: 200).")


                push_access_levels = response_data.get('push_access_levels', [])
                merge_access_levels = response_data.get('merge_access_levels', [])
                
                for access_rule in push_access_levels:
                    if access_rule.get('access_level_description') == username:
                        push_access_rule_id = access_rule.get('id')
                        logging.info(f"Found PUSH access ID to revoke for {username} in project {project_id} on branch {branch}: {push_access_rule_id}")
                        print(f"Found PUSH access ID to revoke for {username} in project {project_id} on branch {branch}: {push_access_rule_id}")
                        break

                for access_rule in merge_access_levels:
                    if access_rule.get('access_level_description') == username:
                        merge_access_rule_id = access_rule.get('id')
                        logging.info(f"Found MERGE access ID to revoke for {username} in project {project_id} on branch {branch}: {merge_access_rule_id}")
                        print(f"Found MERGE access ID to revoke for {username} in project {project_id} on branch {branch}: {merge_access_rule_id}")
                        break
                        
                payload = {}
                revoked_message = []

                if push_access_rule_id:
                    revoked_message.append("PUSH")

                if merge_access_rule_id:
                    revoked_message.append("MERGE")

                if not payload and (not push_access_rule_id and not merge_access_rule_id): 
                    logging.info(f"User '{username}' does not have specific PUSH or MERGE access levels on protected branch 'release/{branch}' in project {project_id} to revoke.")
                    continue
                
                if revoked_message:
                    logging.info(f"Revocation logic for {', '.join(revoked_message)} access for '{username}' in project {project_id} on branch {branch} is currently commented out (Dry Run mode).")

            except requests.exceptions.HTTPError as e:
                logging.error(f"HTTP error during protected branch check for 'release/{branch}' in project {project_id}: {e}. Status code: {e.response.status_code}")
            except requests.exceptions.RequestException as e:
                logging.error(f"Request error while revoking access for branch 'release/{branch}' in project {project_id}: {e}")
            except Exception as e:
                logging.error(f"Unexpected error while revoking access for branch 'release/{branch}' in project {project_id}: {e}")
                
    logging.info(f"--- Finished access revocation for user '{username}' ---")
    return "Complete" 

# MAIN SCRIPT
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="GitLab Protected Branch Access Revocation Tool.")
    parser.add_argument('-g', '--gitlab_token', help='GitLab private token', required=True)
    parser.add_argument('-j', '--jira_list', type=str, help='Comma-separated list of Jira IDs (e.g., JIRA-1,JIRA-2)')
    parser.add_argument('-f', '--filterid', type=str, help='Jira filter ID to fetch a list of Jiras')
    # The '-b' argument seems unused in the main logic flow.
    parser.add_argument('-b', '--branch', nargs="+", help='One or more branches to process (currently unused in main logic)')
    # Optional param
    parser.add_argument("-QA", "--qa_mode", action="store_true", help="This is for QA repo tickets only")
    args = parser.parse_args()
    
    if not args.jira_list and not args.filterid:
        logging.error("Must provide either a list of Jiras (-j/--jira_list) or a filter ID (-f/--filterid).")
        parser.print_help()
        exit(1)

    jira_list = None
    if args.filterid:
        logging.info(f"Fetching Jira list using filter ID: {args.filterid}")
        jira_list_result = get_jirafilterlist(args.filterid)
        if jira_list_result == "error":
            logging.error(f"Exiting due to error fetching Jiras from filter ID {args.filterid}.")
            exit(1)
        jira_list = jira_list_result
    elif args.jira_list:
        jira_list = [x.strip() for x in args.jira_list.split(",")]
        logging.info(f"Using manually provided Jira list: {jira_list}")

    if not jira_list:
        logging.warning("No Jiras were found or provided to process.")
        exit(0)

    print("Jira List: ", jira_list)
    logging.info(f"Jira list entered is: {jira_list}")

    # -------------------------------------------------------JIRA BASED-------------------------------------------------------------------------
    print(f"Total no. of Jiras: {len(jira_list)}")
    if len(jira_list) > config.max_Jiras: # Assuming max_Jiras is defined in config
        logging.error(f"The number of Jiras ({len(jira_list)}) exceeds the maximum allowed limit of {config.max_Jiras}. Exiting.")
        print("This script will work only for {} Jiras at once. Please update the list of Jiras".format(config.max_Jiras))
        exit()
    
    private_token = args.gitlab_token
    results_summary = []

    for i, each_jira in enumerate(jira_list):
        logging.info(f"--- Processing Jira {i+1}/{len(jira_list)}: {each_jira} ---")
        print(f"Processing Jira: {each_jira}")
        
        # 1. Get Jira Assignee (Username)
        user_status, user_result = get_username(each_jira)
        
        if user_status == "error":
            # Error logged inside get_username
            results_summary.append({
            "Jira": each_jira, "branch" : "", "User Status": user_result, "Project Status": "Skipped", 
            "Access Status": "Skipped", "Jira Update Status": "", "FixVersion Update": ""
            })
            continue

        # 2. Get Project and Branch Map from GitLab MRs
        branch_project_status, branch_project_result = get_branch_project_map(each_jira, private_token, args.qa_mode)
        logging.info(f"Branch/Project map result for {each_jira}: {branch_project_result}")
        print(branch_project_result)
        
        if branch_project_status == "error":
            results_summary.append({
                "Jira": each_jira, "branch" : "", "User Status": user_result, "Project Status": branch_project_result, 
                "Access Status": "Skipped", "Jira Update Status": "", "FixVersion Update": ""
            })
            continue


        revoke_access(user_result, branch_project_result, private_token)
        print("--------------------------------------------------------------------------------------------------------------------------")
        results_summary.append({
                "Jira": each_jira, "branch" : "Processed", "User Status": user_result, 
                "Project Status": "Found", "Access Status": "RevocationAttempted", 
                "Jira Update Status": "", "FixVersion Update": ""
        })

    logging.info("--- Script Execution Complete ---")
