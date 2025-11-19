import requests
import json
import re
import argparse
import logging
from itertools import islice
from datetime import datetime
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
project_search = config.project_search
project_search_all = config.project_search_all
target_branch = config.target_branch
username = config.username
password = config.password


def get_username(jira_id):
    url=jira_api_url+"/issue/"+jira_id
    response=requests.get(url,auth=(username,password))
    userresponse_str = response.content.decode('utf-8')
    userresponse_json = json.loads(userresponse_str)
    # if userresponsejson of jira (QA-11341) not equalsto (QA-112341)
    if userresponse_json['key'] != jira_id:
        error_message = f"Failed to retrieve Jira details for {jira_id}. Status Code: {response.status_code}"
        logging.error(error_message)
        return "error", error_message
    assignee = response.json()["fields"]["assignee"]["displayName"]
    print("get_username", assignee)
    return "Success", assignee

def get_branch_project_map(jira_id, private_token, qa_mode=False):
    print("branch_project_map executing...")
    api_url = f"{gitlab_api_url}{project_search_all}{jira_id}"
    mr_response = requests.get(api_url, headers={"PRIVATE-TOKEN": private_token})
    response_data = mr_response.json()
    
    projectId_branch_map = {} 
    projectId_repo_map = {}
    
    if mr_response.status_code != 200 or not mr_response.json():
        if (not projectId_repo_map) and (jira_id.split('-')[0]=='DEV') and (not qa_mode):
            projectId_repo_map.update(config.default_repo)
            limited_repos = dict(islice(projectId_repo_map.items(), 5))
            return "Success", limited_repos
        else:
            error_message = f"Failed to retrieve project details for Jira {jira_id}."
            logging.error(error_message)
            return "error", error_message
    
    for item in response_data:
        project_id = item.get('target_project_id')
        target_branch_full = item.get('target_branch')
        
        if project_id and target_branch_full:
            if target_branch_full.startswith("release/"):
                branch_name = target_branch_full.split('/', 1)[1]
            else:
                continue  # if it is 'develop' then continue

            if project_id not in projectId_branch_map:
                projectId_branch_map[project_id] = []
            
            if branch_name not in projectId_branch_map[project_id]:
                projectId_branch_map[project_id].append(branch_name)

    if len(projectId_branch_map) > 5:
        error_message = f"There are more than Five repos in this {jira_id}, Please check. Limiting to first 5 repos."
        logging.warning(error_message)
        
    limited_map = dict(islice(projectId_branch_map.items(), 5))
    return "Success", limited_map
    
# filter_id based
def get_jirafilterlist(filterid):
    filterstring = f"{jira_api_url}/search?jql=filter={filterid}&fields=key"
    response = requests.get(filterstring, auth=(username, password))
    if response.status_code == 200:
        filterresponse_str = response.content.decode('utf-8')
        filterresponse_json = json.loads(filterresponse_str)
        jiraslist = []
        for item in filterresponse_json['issues']:
            jiraslist.append(item['key'])
        return jiraslist
    else:
        return "error"
    

# Revoke Script
def revoke_access(username, branch_project_id_map, private_token):
    print("---------------Fetching details for revoke---------------------")
    print("User to revoke", username)
    print("Branch and project map details", branch_project_id_map)

    for project_id, branches in branch_project_id_map.items():
        print(f"Processing Project ID: {project_id}")
        for branch in branches:
            full_branch_name = f"release%2F{branch}"
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
                    logging.warning(f"Branch '{branch}' is not protected in project ID {project_id}. Skipping revocation.")
                    continue
                    
                response.raise_for_status()
                response_data = response.json()

                for access_rule in response_data.get('push_access_levels', []):
                    if access_rule.get('access_level_description') == username:
                        push_access_rule_id = access_rule.get('id')
                        print(f"Found PUSH access ID to revoke for {username} in project {project_id} on branch {branch}: {push_access_rule_id}")
                        break

                for access_rule in response_data.get('merge_access_levels', []):
                    if access_rule.get('access_level_description') == username:
                        merge_access_rule_id = access_rule.get('id')
                        print(f"Found MERGE access ID to revoke for {username} in project {project_id} on branch {branch}: {merge_access_rule_id}")
                        break

            #     payload = {}
            #     revoked_message = []

            #     if push_access_rule_id:
            #         payload["allowed_to_push"] = [{"id": push_access_rule_id, "_destroy": True}]
            #         revoked_message.append("PUSH")

            #     if merge_access_rule_id:
            #         payload["allowed_to_merge"] = [{"id": merge_access_rule_id, "_destroy": True}]
            #         revoked_message.append("MERGE")

                
            #     if not payload:
            #         logging.info(f"User '{username}' does not have specific PUSH or MERGE access levels on branch '{branch}' in project {project_id} to revoke.")
            #         continue

            #     print(f"Sending PATCH payload to revoke access: {payload}")
            #     destroy_response = requests.patch(base_url, headers=headers, json=payload)

            #     if destroy_response.status_code == 200:
            #         logging.info(f"Successfully revoked {', '.join(revoked_message)} access for '{username}' on branch '{branch}' in project {project_id}")
            #     else:
            #         logging.error(
            #             f"Failed to remove access for '{username}' on branch '{branch}' in project {project_id}."
            #             f"Status code: {destroy_response.status_code}, Response: {destroy_response.text}"
            #         )

            except requests.exceptions.RequestException as e:
                logging.error(f"Request error while revoking access for branch '{branch}' in project {project_id}: {e}")
            except Exception as e:
                logging.error(f"Unexpected error while revoking access for branch '{branch}' in project {project_id}: {e}")


# MAIN SCRIPT
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('-g', '--gitlab_token', help='GitLab private token')
    parser.add_argument('-j', '--jira_list', type=str)
    parser.add_argument('-f', '--filterid', type=str)
    parser.add_argument('-b', '--branch', nargs="+", help='One or more items to process')
    # Optional param
    parser.add_argument("-QA", "--qa_mode", action="store_true", help="This is for QA repo tickets only")
    args = parser.parse_args()

    jira_list=None

    if args.filterid:
        jira_list=get_jirafilterlist(args.filterid)
    if args.jira_list:
        jira_list=args.jira_list
        jira_list = [x.strip() for x in jira_list.split(",")]

    print("Jira List: ", jira_list)

    # -------------------------------------------------------JIRA BASED-------------------------------------------------------------------------
    print("Jira list entered is: {}\n".format(jira_list))
    print(f"Total no. of Jiras: {len(jira_list)}")
    private_token = args.gitlab_token
    for each_jira in jira_list:
        print(each_jira+" ")
    if len(jira_list) > config.max_Jiras:
        print("This script will work only for 30 Jiras at once. Please update the list of Jiras")
        exit()
    
    results_summary=[]

    for each_jira in jira_list:
        user_status, user_result = get_username(each_jira)
        if user_status == "error":
            logging.error(user_result)
            results_summary.append({
            "Jira": each_jira,
            "branch" : "",
            "User Status": user_result,
            "Project Status": "",
            "Access Status": "",
            "Jira Update Status": "",
            "FixVersion Update": ""
            })
            continue

        # loop thorugh each release branch and pass it to project_id function
        branch_project_status, branch_project_result = get_branch_project_map(each_jira, private_token, args.qa_mode)
        print(branch_project_result)
        if branch_project_status == "error":
            logging.error(branch_project_result)
            results_summary.append({
                "Jira": each_jira,
                "branch" : "",
                "User Status": user_result,
                "Project Status": branch_project_result,
                "Access Status": "",
                "Jira Update Status": "",
                "FixVersion Update": ""
            })
            continue

        revoke_result = revoke_access(user_result, branch_project_result, private_token)
        print("------------------------------------------")
        print("------------------------------------------")
        # # if access_status == "error":
        # #     logging.error(access_result)
        # #     results_summary.append({
        # #     "Jira": each_jira,
        # #     "branch" : "",
        # #     "User Status": user_result,
        # #     "Project Status": project_result,
        # #     "Access Status": access_status,
        # #     "Jira Update Status": "",
        # #     "FixVersion Update": ""
        # #     })
        # #     continue