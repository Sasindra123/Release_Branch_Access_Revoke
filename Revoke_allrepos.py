import requests
import json
import re
import sys
import argparse
import logging
from itertools import islice
from datetime import datetime
import config

# log_file_name = datetime.now().strftime('access_revoke_%Y%m%d_%H%M%S.log')
# logging.basicConfig(
#     filename=log_file_name,
#     level=logging.INFO,
#     format='%(asctime)s - %(levelname)s - %(message)s'
# )
# console_handler = logging.StreamHandler()
# console_handler.setLevel(logging.INFO)
# console_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
# logging.getLogger().addHandler(console_handler)

gitlab_api_url = config.gitlab_api_url


# def fetch_active_branches():
#     scba_api_url = "https://scdb.vaultdev.com/default/latest/manifest/active_versions"
#     scba_api_data = None
    
#     try:
#         response = requests.get(scba_api_url)
#         response.raise_for_status() 
#         scba_api_data = response.json()
#     except Exception as e:
#         print(f"Error fetching live data ({e}). Could not retrieve data from API.")
#         scba_api_data = {"pipeline": []}
            
#     pipeline_versions = [item["name"] for item in scba_api_data["pipeline"]]
#     target_branches = []

#     def is_internal_release(version):
#         internal_releases = ['1.1', '2.1', '3.1']
#         parts = version.split('.')
#         if len(parts) < 3:
#             return False
#         sprint_patch = f"{parts[1]}.{parts[2]}"
#         return sprint_patch in internal_releases
    
#     def get_base_sprint(version):
#         parts = version.split('.')
#         return f"{parts[0]}.{parts[1]}"

#     if is_internal_release(pipeline_versions[0]):
#         target_branches = pipeline_versions[:3] 
        
#     elif is_internal_release(pipeline_versions[1]):
#         target_branches.append(pipeline_versions[0])
#         target_branches.append(pipeline_versions[2])
#         target_branches.append(pipeline_versions[3])
        
#     else:
#         target_branches.append(pipeline_versions[0])
#         target_branches.append(pipeline_versions[1])
    
#         base_sprint = get_base_sprint(pipeline_versions[0]) 
#         print(base_sprint)
#         target_x0_version = f"{base_sprint}.0"
        
#         found_x0 = None
#         for version in pipeline_versions:
#             if version == target_x0_version:
#                 found_x0 = version
#                 break
        
#         if found_x0:
#             target_branches.append(found_x0)
#     return target_branches


def revoke_all_access(branches, repo_list, private_token):
    for project_id,project_name in repo_list.items():
        print(f"Project_id: {project_id}, Project_name: {project_name} being revoked....")
        for branch in branches:
            full_branch_name = f"release%2F{branch}"
            print(full_branch_name)
            base_url = f"{gitlab_api_url}/projects/{project_id}/protected_branches/{full_branch_name}"
            headers = {
                "PRIVATE-TOKEN": private_token,
                "Content-Type": "application/json"
            }

            user_push_ids = []
            user_merge_ids = []
            revoked_usernames = []

            try:
                response = requests.get(base_url, headers=headers)
                if response.status_code == 404:
                    logging.warning(f"Branch 'release/{branch}' is not protected in project ID {project_id} (404 Not Found). Skipping revocation.")
                    continue
                response.raise_for_status() 
                response_data = response.json()

                push_access_levels = response_data.get('push_access_levels', [])
                for access_rule in push_access_levels:
                    if access_rule.get('user_id') is not None and access_rule.get('group_id') is None:
                        user_push_ids.append(access_rule['id'])
                        username = access_rule.get('access_level_description')
                        if username and username not in revoked_usernames:
                            revoked_usernames.append(username)
                        print(f"Found PUSH access ID {access_rule['id']} for user '{username}' to revoke.")

                merge_access_levels = response_data.get('merge_access_levels', [])
                for access_rule in merge_access_levels:
                    if access_rule.get('user_id') is not None and access_rule.get('group_id') is None:
                        user_merge_ids.append(access_rule['id'])
                        username = access_rule.get('access_level_description')
                        if username and username not in revoked_usernames:
                            revoked_usernames.append(username)
                        print(f"Found MERGE access ID {access_rule['id']} for user '{username}' to revoke.")

                payload = {}
                if user_push_ids:
                    payload["allowed_to_push"] = [{"id": rule_id, "_destroy": True} for rule_id in user_push_ids]
                if user_merge_ids:
                    payload["allowed_to_merge"] = [{"id": rule_id, "_destroy": True} for rule_id in user_merge_ids]

                print(payload)

                total_revoked_count = len(user_push_ids) + len(user_merge_ids)
                if total_revoked_count == 0:
                    print(f"No specific user access rules found to revoke on branch '{branch}'.")
                    exit()
                
                print("\n\nAttempting to revoke access for users...")
                destroy_response = requests.patch(base_url, headers=headers, json=payload)
                
                if destroy_response.status_code == 200:
                    usernames_list = ', '.join(revoked_usernames)
                    message = f"Successfully revoked {usernames_list} user access rules on branch '{branch}'."
                    print(message)
                else:
                    error_message = f"Failed to remove access on '{branch}'. Status: {destroy_response.status_code}"
                    logging.error(error_message)
                    print(f"Failed to remove access on '{branch}'. Status: {destroy_response.status_code}")
                
            except requests.exceptions.HTTPError as e:
                print(f"HTTP error during protected branch check for 'release/{branch}' in project {project_id}: {e}.")
            except requests.exceptions.RequestException as e:
                print(f"Request error while revoking access for branch 'release/{branch}' in project {project_id}: {e}")
            except Exception as e:
                print(f"Error occured while revoking the branch access.")


# Main Function
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="GitLab Protected Branch Access Revocation Tool.")
    parser.add_argument('-g', '--gitlab_token', help='GitLab private token')
    parser.add_argument('-j', '--jira_list', type=str, help='Comma-separated list of Jira IDs (e.g., JIRA-1,JIRA-2)')
    parser.add_argument('-f', '--filterid', type=str, help='Jira filter ID to fetch a list of Jiras')
    parser.add_argument('-v', '--vault', action='store_true', help='Process DEV-repos (Flag)')
    parser.add_argument('-q', '--qa', action='store_true', help='Process DEV-repos (Flag)')
    parser.add_argument('-s', '--safety', action='store_true', help='Process Safety-repos (Flag)')
    parser.add_argument('-c', '--cp', action='store_true', help='Process CP-repos (Flag)')
    parser.add_argument('-l', '--lims', action='store_true', help='Process LIMS-repos (Flag)')
    
    args = parser.parse_args()
    gitlab_private_token = args.gitlab_token
    all_groups = config.all_repos
    

    selected_groups = []
    if args.qa:
        selected_groups.append("QA")
    if args.vault:
        selected_groups.append("DEV")
    if args.safety:
        selected_groups.append("Safety")
    if args.cp:
        selected_groups.append("CP")
    if args.lims:
        selected_groups.append("Lims")

    # branches_to_revoke = fetch_active_branches()
    branches_to_revoke = ['24.3.5']
    print("Branches need to revoke: ", branches_to_revoke)

    all_groups = all_groups[0]
    
    for group_name in selected_groups:  # ["DEV" /"Safety" /"CP" /"LIMS"]
        if group_name in all_groups:
            repos_list = all_groups[group_name]

            # Revoking for each repository list in the groups
            print(f"\n\nRevoking the access for {group_name} Repo")
            for repo in repos_list:
                print(repos_list)
                print(repo)
                # result = revoke_all_access(branches_to_revoke, repo_list, gitlab_private_token)