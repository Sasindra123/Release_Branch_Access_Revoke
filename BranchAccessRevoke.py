import requests
import json
import re
import sys
import argparse
import logging
from itertools import islice
from datetime import datetime
import config

# Generate a timestamped filename for the log file
log_filename = datetime.now().strftime('access_revoke_%Y%m%d_%H%M%S.log')
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
project_search_all = config.project_search_all
username = config.username
password = config.password


def get_username(jira_id):
    # Retrieves the assignee's display name from a Jira ticket.
    url = f"{jira_api_url}/issue/{jira_id}"
    try:
        response = requests.get(url, auth=(username, password))
        if response.status_code == 200:
            logging.info(f"Successfully retrieved Jira details for {jira_id}.")
            userresponse_json = response.json()
            
            if userresponse_json['key'] != jira_id:
                error_message = f"Mismatched Jira ID. Requested: {jira_id}, Received: {userresponse_json['key']}. Status Code: {response.status_code}"
                logging.error(error_message)
                return "error", error_message
                
            assignee = userresponse_json["fields"]["assignee"]["displayName"]
            logging.info(f"Assignee found for {jira_id}: {assignee}")
            return "Success", assignee
        else:
            error_message = f"Failed to retrieve Jira details for {jira_id}. Status Code: {response.status_code}. Response: {response.text}"
            logging.error(error_message)
            return "error", error_message
            
    except requests.exceptions.RequestException as e:
        error_message = f"Request error while fetching Jira details for {jira_id}: {e}"
        logging.error(error_message)
        return "error", error_message
    
# get jira state from the jira
def get_jira_state(jira_id):
    url = f"{jira_api_url}/issue/{jira_id}"
    try:
        response = requests.get(url, auth=(username, password))
        if response.status_code == 200:
            status_response = response.json()  
            name=status_response.get('fields',{}).get('status',{}).get('name')
            if name == 'Closed' or name == 'Resolved':
                logging.info(f"Jira issue is {name}. Proceeding with branch access revoking")
                return name
            else:
                logging.warning(f"Jira issue is {name}. Can't revoke access until the issue is RESOLVED / CLOSED")
                sys.exit()
        else:
            error_message = f"Failed to retrieve Jira status for {jira_id}. Status Code: {response.status_code}. Response: {response.text}"
            logging.error(error_message)
            return error_message
            
    except requests.exceptions.RequestException as e:
        error_message = f"Request error while fetching Jira details for {jira_id}: {e}"
        logging.error(error_message)
        return "error", error_message

    
# get branch_name from jira for unlinked mr.
def get_branch_from_jira(jira_id):
    url = f"{jira_api_url}/issue/{jira_id}"
    try:
        response = requests.get(url, auth=(username, password))
        if response.status_code == 200:
            response_json = response.json()

            # get 'name' field from fixVersions
            fixversion_data=response_json.get('fields',{}).get('fixVersions',[])
            if not fixversion_data:
                logging.error(f"FixVersion field is empty or invalid {fixversion_data}. Can't proceed with branch access revoke")
                sys.exit()
            if fixversion_data:
                branches = [
                    item.get('name').replace('R', '.')
                    for item in fixversion_data 
                    if item.get('name')  
                ]
            return "Success",branches
            
        else:
            error_message = f"Failed to retrieve Jira details for {jira_id}. Status Code: {response.status_code}. Response: {response.text}"
            logging.error(error_message)
            return "error", error_message
        
    except requests.exceptions.RequestException as e:
        error_message = f"Request error while fetching Jira details for {jira_id}: {e}"
        logging.error(error_message)
        return "error", error_message
    except Exception as e:
        error_message = f"Unexpected error in get_branch_from_jira for {jira_id}: {e}"
        logging.error(error_message)
        return "error", error_message

# Retrieves Gitlab projects and release branches associated with a Jira ID via MR search.
def get_branch_project_map(jira_id, private_token, qa_mode=False):
    api_url = f"{gitlab_api_url}{project_search_all}{jira_id}"
    projectId_branch_map = {} 
    projectId_repo_map = {}
    try:
        mr_response = requests.get(api_url, headers={"PRIVATE-TOKEN": private_token}) 
        if mr_response.status_code != 200 or not mr_response.json():
            error_message = f"MR is Not Linked to {jira_id}. Status Code: {mr_response.status_code}. Response: {mr_response.text}"
            logging.error(error_message)

            logging.info(f"Response: {mr_response.status_code} Without MR executing....")
            # Logic for DEV tickets with no MRs
            if (not projectId_repo_map) and (jira_id.split('-')[0] == 'DEV') and (not qa_mode):
                logging.info("Entering into default repo execution...")

                projectId_repo_map.update(config.default_repo)
                limited_repos = dict(islice(projectId_repo_map.items(), 5))
                branch_status, branches_from_jira=get_branch_from_jira(jira_id)

                if branch_status == "Success":
                    for project_id in limited_repos.keys():
                        projectId_branch_map[project_id] = branches_from_jira
                return "Success", projectId_branch_map 
            else:
                logging.error(f"Cannot proceed with default repos for {jira_id}: Failed to retrieve branch name from QA Jira.")
                return "error", error_message
            
        else:
                logging.info(f"Response: {mr_response.status_code} With MR executing....")
                response_data = mr_response.json()
                if not response_data:
                    logging.error("No merged mr found in jira to process ...exiting")
                    sys.exit(1)
                
                # logging.info(f"Successfully retrieved {len(response_data)} merge requests for {jira_id}.")
                repo_name=""
                for item in response_data:
                    project_id = item.get('target_project_id')
                    repo_url = item.get('web_url')
                    match = re.search(r'\/([^\/]+)\/-\/', repo_url)
                    if match:
                        repo_name = match.group(1)
                    else:
                        repo_name = "Repository name not found"
                    
                    target_branch_full = item.get('target_branch')
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
                print("Repository Name : ",repo_name)

                if not projectId_branch_map:
                    error_message = f"No release branches found for Jira {jira_id} in any merge request."
                    logging.warning(error_message)
                    return "error", error_message
                    
                if len(projectId_branch_map) > 5:
                    warning_message = f"There are more than five repos associated with {jira_id} ({len(projectId_branch_map)}). Limiting to the first 5 repos."
                    logging.warning(warning_message)
                    
                limited_map = dict(islice(projectId_branch_map.items(), 5)) # processsing only first 5 projects
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
    results=[]
    # Revokes push/merge access for a user on protected GitLab branches.
    logging.info(f"--- Starting access revocation for user '{username}' ---")
    for project_id, branches in branch_project_id_map.items():
        logging.info(f"Processing Project ID: {project_id}")

        for branch in branches:
            full_branch_name = f"release%2F{branch}"
            logging.info(f"Checking protected branch: {full_branch_name}")
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


                push_access_levels = response_data.get('push_access_levels', [])
                for access_rule in push_access_levels:
                    if access_rule.get('access_level_description') == username:
                        push_access_rule_id = access_rule.get('id')
                        logging.info(f"Found PUSH access ID to revoke for {username} in project {project_id} on branch {branch}: {push_access_rule_id}")
                        break

                merge_access_levels = response_data.get('merge_access_levels', [])
                for access_rule in merge_access_levels:
                    if access_rule.get('access_level_description') == username:
                        merge_access_rule_id = access_rule.get('id')
                        logging.info(f"Found MERGE access ID to revoke for {username} in project {project_id} on branch {branch}: {merge_access_rule_id}")
                        break
                        
                # destroy the user using patch
                payload = {}
                revoked_message = []

                if push_access_rule_id:
                    payload["allowed_to_push"] = [{"id": push_access_rule_id, "_destroy": True}]
                    revoked_message.append("PUSH")

                if merge_access_rule_id:
                    payload["allowed_to_merge"] = [{"id": merge_access_rule_id, "_destroy": True}]
                    revoked_message.append("MERGE")
              
                if not payload: # if no user in Gitlab for protected branch
                    logging.info(f"User '{username}' does not have specific PUSH or MERGE access levels on branch '{branch}' in project {project_id} to revoke.")
                    continue
                
                # PATCH Request
                destroy_response = requests.patch(base_url, headers=headers, json=payload)

                if destroy_response.status_code == 200:
                    message=f"Successfully revoked {', '.join(revoked_message)} access for '{username}' on branch '{branch}' in project {project_id}"
                    logging.info(message)
                    results.append(("Success",message))
                else:
                    error_message = f"Failed to remove access levels for repository '{project_id}'. Status Code: '{response.status_code}', Response: '{response.text}'."
                    logging.error(error_message)
                    results.append(("error", error_message))
               
                if not payload and (not push_access_rule_id and not merge_access_rule_id): 
                    logging.info(f"User '{username}' does not have specific PUSH or MERGE access levels on protected branch 'release/{branch}' in project {project_id} to revoke.")
                    continue

            except requests.exceptions.HTTPError as e:
                logging.error(f"HTTP error during protected branch check for 'release/{branch}' in project {project_id}: {e}. Status code: {e.response.status_code}")
            except requests.exceptions.RequestException as e:
                logging.error(f"Request error while revoking access for branch 'release/{branch}' in project {project_id}: {e}")
            except Exception as e:
                logging.error(f"Unexpected error while revoking access for branch 'release/{branch}' in project {project_id}: {e}")
    logging.info(f"--------------- Finished access revocation for user '{username}' ----------------") 
    return results

# MAIN SCRIPT
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="GitLab Protected Branch Access Revocation Tool.")
    parser.add_argument('-g', '--gitlab_token', help='GitLab private token', required=True)
    parser.add_argument('-j', '--jira_list', type=str, help='Comma-separated list of Jira IDs (e.g., JIRA-1,JIRA-2)')
    parser.add_argument('-f', '--filterid', type=str, help='Jira filter ID to fetch a list of Jiras')
    # The '-b' argument seems unused in the main logic flow.
    parser.add_argument('-b', '--branch', nargs="+", help='')
    # Optional param
    parser.add_argument("-QA", "--qa_mode", action="store_true", help="This is for QA repo tickets only")
    args = parser.parse_args()
    private_token = args.gitlab_token
    
    if not args.jira_list and not args.filterid:
        logging.warning("Must provide either a list of Jiras (-j/--jira_list) or a filter ID (-f/--filterid).")
        parser.print_help()
        exit(1)

    if args.jira_list and args.filterid:
        logging.warning("Must Provide either a Jira List or a Filter ID, but not both arguments to the script.")
        exit(1)

    jira_list = None
    if args.filterid:  # FILTER ID BASED
        logging.info(f"Fetching list of Jiras from Filter ID: {args.filterid}")
        jira_list_result = get_jirafilterlist(args.filterid)
        if jira_list_result == "error":
            logging.error(f"Exiting due to error fetching Jiras from filter ID {args.filterid}.")
            exit(1)
        jira_list = jira_list_result
    elif args.jira_list: # JIRA BASED
        jira_list = [x.strip() for x in args.jira_list.split(",")]
        logging.info(f"List of Jiras provided: {jira_list}")
    if not jira_list: # NONE
        logging.warning("No Jiras were found or provided to process.")
        exit(0)

    logging.info(f"Jira list : {jira_list}")
    if len(jira_list) > config.max_Jiras: 
        logging.error(f"The number of Jiras ({len(jira_list)}) exceeds the maximum allowed limit of {config.max_Jiras}. Exiting.")
        exit()
    
    
    results_summary = []
    for i, each_jira in enumerate(jira_list):
        logging.info(f"--- Processing Jira {i+1}/{len(jira_list)}: {each_jira} ---")

        # USER RETRIEVAL
        user_status, user_result = get_username(each_jira)
        if user_status == "error":
            results_summary.append({
            "Jira": each_jira, "User Status": user_result,
            })
            continue

        # Jira state - Resolved for DEV Jira
        status_result = get_jira_state(each_jira)
        if status_result == "error":
            results_summary.append({
                "Jira": each_jira, "User Status": user_result, "Jira status" : status_result,
            })
            continue
            

        # BRANCH-PROJECT MAP 
        branch_project_status, branch_project_result = get_branch_project_map(each_jira, private_token, args.qa_mode)
        logging.info(f"Branch/Project map result for {each_jira}: {branch_project_result}")
        
        if branch_project_status == "error":
            results_summary.append({
                "Jira": each_jira, "User Status": user_result, "Jira status" : status_result, "Branch_Project Status": branch_project_result, 
            })
            continue

        # REVOKE BRANCH ACCESS
        result = revoke_access(user_result, branch_project_result, private_token)
        revoke_status = "Skipped/No Access Found"
        if result:
            revoke_status = result[0][0]
        print("Revoke status :", revoke_status)

        if revoke_status == "error":
            logging.error(result)
            results_summary.append({
            "Jira": each_jira,
            "User Status": user_result,
            "Jira status" : status_result,
            "Branch_Project Status": branch_project_result,
            "Revoke Status": revoke_status
            })
            continue


        results_summary.append({
                "Jira": each_jira, "User Status": user_result, "Branch_Project Status": branch_project_result, "Revoke Status": revoke_status
        })
        for result in results_summary:
            logging.info(f"Results Summary: Jira : %s, User: %s, Project-branch map result: %s,  Revoke Status: %s", 
                         result['Jira'], result['User Status'], result['Branch_Project Status'],result['Revoke Status'])
    