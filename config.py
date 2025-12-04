gitlab_api_url = "https://gitlab.veevadev.com/api/v4"
jira_api_url = "https://jira.veevadev.com/rest/api/2"
project_search_all = "/merge_requests?scope=all&state=merged&in=title&search_type=advanced&search=" 
username = "VaultApiUser"
password = "woozle11"
max_Jiras = 100
default_repo = {2939:'automation-platform-pipelines'}
all_repos = [
    {
        # "DEV": [
        #     {"314": "Vault"}
        # ],
        "QA": [
            {"328": "VaultAutomationTests",
             "2939": "automation-platform-pipelines"}
        ],
        # "Safety": [
        #     {
        #         "719": "vaultapp-safety",
        #         "1820": "safety-management-gateway",
        #         "1859": "safety-ai-infra",
        #         "2621": "safety-reporting-infra",
        #         "2097": "safety-common-infra"
        #     }
        # ],
        # "CP": [
        #     {
        #         "1161": "regulatoryone-tools",
        #         "979": "claims",
        #         "2748": "Claims DevOps",
        #         "1132": "Claims Documentation"
        #     }
            
        # ],
        # "Lims": [
        #     {"2717": "LIMS"}
        # ]
    }
]

