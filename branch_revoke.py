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
    print(response)
    userresponse_str = response.content.decode('utf-8')
    userresponse_json = json.loads(userresponse_str)
    # if userresponsejson of jira (QA-11341) not equalsto (QA-112341)
    if userresponse_json['key'] != jira_id:
        error_message = f"Failed to retrieve Jira details for {jira_id}. Status Code: {response.status_code}"
        logging.error(error_message)
        return "error", error_message
    assignee = response.json()["fields"]["assignee"]["displayName"]
    print(assignee)
    return "Success", assignee

def get_branches(jira,token):
    url=f"{gitlab_api_url}{project_search}{jira}"
    response=requests.get(url,headers={"PRIVATE-TOKEN": token})
    response_data=response.json()
    
    release_mrs=[]
    for item in response_data:
        target_branch=item.get('target_branch')
        print(target_branch)

        if target_branch and target_branch.startswith("release/"):
            release_mrs.append(target_branch.split('/')[1])
    return release_mrs

def get_project_id(jira_id,private_token,qa_mode=False):
    # here, we get the mr's that are in "merged state"
    api_url = f"{gitlab_api_url}{project_search_all}{jira_id}"
    mr_response = requests.get(api_url, headers={"PRIVATE-TOKEN": private_token})
    response_data = mr_response.json()
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
    # Mapping project IDs to repo names
    # Iterate through each dictionary in the list
    for item in response_data:
        # Access the 'target_project_id' key from each dictionary
        project_id = item.get('target_project_id')
        repo_url = item.get('web_url')
        match = re.search(r'\/([^\/]+)\/-\/', repo_url)
        if match:
            repo_name = match.group(1)
        else:
            repo_name = "Repository name not found"

        # Check if project_id is not None (to handle cases where 'target_project_id' key might be missing)
        if project_id is not None:
            # Add the project_id to the set
            projectId_repo_map[project_id] = repo_name
    if len(projectId_repo_map) > 5:
        error_message = f"There are more than Five repos in this {jira_id}, Please check"
        logging.warning(error_message)
    #Limit the program to give only access to the first 5 repos
    limited_repos = dict(islice(projectId_repo_map.items(), 5))
    return "Success", list(limited_repos.keys())[0]
    
# filter_id based
def get_filterid_jiras(filterid):
    pass

    







# Revoke Script
def revoke_access(username, branches, project_id, private_token):
    print("---------------Fetching details for revoke---------------------")
    print("Project_id from MR",project_id)
    print("Username from jira",username)
    for branch in branches:
        full_branch_name=f"release%2F{branch}"
        print(full_branch_name)
        base_url = f"{gitlab_api_url}/projects/{project_id}/protected_branches/{full_branch_name}"
        headers = {
            "PRIVATE-TOKEN": private_token,
            "Content-Type": "application/json"
        }
 
        try:
            response = requests.get(base_url, headers=headers)
            if response.status_code == 404:
                logging.warning(f"Branch '{branch}' is not protected in project ID {project_id}. Skipping revocation.")
                return 

            response.raise_for_status()
            response_data = response.json()
            access_id = None
            access_user_id = None
            for access_rule in response_data.get('push_access_levels', []):
                if access_rule.get('access_level_description') == username:
                    access_user_id = access_rule.get('user_id')
                    access_id = access_rule.get('id')
                    break
            print("access_id to revoke : ", access_id)
            print("access_user_id to revoke : ",access_user_id)

            push_access_levels = response_data.get("push_access_levels", [])
            merge_access_levels = response_data.get("merge_access_levels", [])

            print("push_access_levels", push_access_levels)
            print("merge_access_levels", merge_access_levels)

            allowed_to_push = []
            allowed_to_merge = []

            # print(push_access_levels.get("user_id"))
            # print(push_access_levels.get("id"))

            # for access in push_access_levels:
            #     if access.get("user_id") and access.get("id"):
            #         allowed_to_push.append({"id": access["id"], "_destroy": True})

            # for access in merge_access_levels:
            #     if access.get("user_id") and access.get("id"):
            #         allowed_to_merge.append({"id": access["id"], "_destroy": True})

            # if allowed_to_push or allowed_to_merge:
            #     payload = {}
            #     if allowed_to_push:
            #         payload["allowed_to_push"] = allowed_to_push
            #     if allowed_to_merge:
            #         payload["allowed_to_merge"] = allowed_to_merge

            #     destroy_response = requests.patch(base_url, headers=headers, json=payload)
            #     if destroy_response.status_code == 200:
            #         for user_id, user_name in push_users:
            #             logging.info(f"Removed PUSH access for {user_name} (ID:{user_id}) on branch '{branch_name}'")
            #         for user_id, user_name in merge_users:
            #             logging.info(f"Removed MERGE access for {user_name} (ID:{user_id}) on branch '{branch_name}'")
            #     else:
            #         logging.error(
            #             f"Failed to remove access on branch '{branch_name}'."
            #             f"Status code: {destroy_response.status_code}, Response: {destroy_response.text}"
            #         )
            # else:
            #     logging.info(f"No push or merge access to revoke on branch '{branch_name}'")

        except requests.exceptions.RequestException as e:
            logging.error(f"Request error while revoking access for branch '{branch}': {e}")
        except Exception as e:
            logging.error(f"Unexpected error while revoking access for branch '{branch}': {e}")


# MAIN SCRIPT
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('-g', '--gitlab_token', help='GitLab private token')
    parser.add_argument('-j', '--jira_list', type=str)
    parser.add_argument('-f', '--filterid', type=str)
    parser.add_argument('-b', '--branches', nargs="+", help='One or more items to process')
    # Optional param
    parser.add_argument("-QA", "--qa_mode", action="store_true", help="This is for QA repo tickets only")
    args = parser.parse_args()

    if args.filterid:
        jiras_list=[]
        jiras_list.append(get_filterid_jiras(args.filterid))
        
    # -------------------------------------------------------JIRA BASED-------------------------------------------------------------------------
    jira_list = [x.strip() for x in args.jira_list.split(",")]
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
        
        #get branch details
        branches=get_branches(each_jira,private_token)
        print(branches)

        # loop thorugh each release branch and pass it to project_id function
        project_status, project_result = get_project_id(each_jira, private_token, args.qa_mode)
        if project_status == "error":
            logging.error(project_result)
            results_summary.append({
                "Jira": each_jira,
                "branch" : "",
                "User Status": user_result,
                "Project Status": project_result,
                "Access Status": "",
                "Jira Update Status": "",
                "FixVersion Update": ""
            })
            continue

        filterid_result= get_filterid_jiras(args.filterid)

            
        revoke_result = revoke_access(user_result, branches, project_result, private_token)
        print(revoke_result)
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

        

       
       
            
        







    
   






