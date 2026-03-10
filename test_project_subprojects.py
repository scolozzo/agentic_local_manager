from app_core.project_subprojects import normalize_project_subprojects, upsert_subproject_config


def test_upsert_subproject_config_stores_repo_url_and_workspace_dir():
    data = upsert_subproject_config(
        {},
        {
            "id": "API_CORE",
            "project_id": "HOSTING",
            "label": "API Core",
            "repo_url": "https://gitlab.com/org/api-core.git",
            "stack_key": "BACK",
            "substack": "api",
        },
    )

    item = data["API_CORE"]
    assert item["repo_url"] == "https://gitlab.com/org/api-core.git"
    assert item["workspace_dir"].endswith("workspaces\\hosting\\api_core")


def test_normalize_project_subprojects_exposes_repo_url_and_workspace_dir():
    items = normalize_project_subprojects(
        {
            "API_CORE": {
                "project_id": "HOSTING",
                "label": "API Core",
                "repo_url": "https://gitlab.com/org/api-core.git",
                "workspace_dir": "C:/tmp/workspaces/hosting/api_core",
                "stack_key": "BACK",
                "substack": "api",
            }
        }
    )

    assert items[0]["repo_url"] == "https://gitlab.com/org/api-core.git"
    assert items[0]["workspace_dir"] == "C:/tmp/workspaces/hosting/api_core"
