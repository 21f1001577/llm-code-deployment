import os
import subprocess
import tempfile
import time
import requests
from github import Github, GithubException


def create_and_push_repo(repo_name, files, evaluation_data=None, update_existing=False):
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        raise RuntimeError("GITHUB_TOKEN not set")

    user = Github(token).get_user()
    print(f"Authenticated as: {user.login}")

    try:
        user_login = user.login
        user_email = f"{user_login}@users.noreply.github.com"
        subprocess.run(["git", "config", "user.name", user_login], check=False)
        subprocess.run(["git", "config", "user.email", user_email], check=False)
    except Exception as git_cfg_err:
        print(f"Warning: Failed to configure git identity: {git_cfg_err}")

    repo = None
    try:
        if update_existing:
            repo = user.get_repo(repo_name)
            print(f"Updating existing repo: {repo.html_url}")
        else:
            repo = user.create_repo(
                repo_name,
                description="Auto-generated repo for IITM LLM Deployment",
                private=False,
            )
            print(f"Created new repo: {repo.html_url}")
    except GithubException as e:
        if e.status == 422 and "name already exists" in str(e.data).lower():
            repo = user.get_repo(repo_name)
            print(f"Reusing existing repo: {repo.html_url}")
        else:
            print(f"Repo operation failed: {e.data}")
            return None, None, None

    # Workflow for GitHub Pages
    workflow_content = """name: Deploy Pages

on:
  push:
    branches: [ main ]

permissions:
  contents: read
  pages: write
  id-token: write

concurrency:
  group: "pages"
  cancel-in-progress: true

jobs:
  deploy:
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/configure-pages@v4
      - uses: actions/upload-pages-artifact@v3
        with:
          path: .
      - uses: actions/deploy-pages@v4
        id: deployment
"""
    files[".github/workflows/pages.yml"] = workflow_content

    try:
        with tempfile.TemporaryDirectory() as tmp:
            for name, content in files.items():
                file_path = os.path.join(tmp, name)
                os.makedirs(os.path.dirname(file_path), exist_ok=True)
                with open(file_path, "w") as f:
                    f.write(content)

            subprocess.check_call(["git", "init"], cwd=tmp)
            subprocess.check_call(["git", "add", "."], cwd=tmp)
            subprocess.check_call(["git", "commit", "-m", "Automated commit"], cwd=tmp)
            subprocess.check_call(["git", "branch", "-M", "main"], cwd=tmp)

            push_url = f"https://{token}@github.com/{user.login}/{repo_name}.git"
            subprocess.check_call(["git", "remote", "add", "origin", push_url], cwd=tmp)
            subprocess.check_call(["git", "push", "-u", "origin", "main", "--force"], cwd=tmp)

            commit_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=tmp).decode().strip()
    except Exception as e:
        print(f"Git push failed: {e}")
        return None, None, None

    pages_url = f"https://{user.login}.github.io/{repo_name}/"

    try:
        requests.put(
            f"https://api.github.com/repos/{user.login}/{repo_name}/pages",
            headers={"Authorization": f"token {token}", "Accept": "application/vnd.github+json"},
            json={"source": {"branch": "main", "path": "/"}},
        )
    except Exception as e:
        print(f"Pages enablement skipped: {e}")

    # Evaluation callback
    if evaluation_data:
        payload = {
            "email": evaluation_data["email"],
            "task": evaluation_data["task"],
            "round": evaluation_data["round"],
            "nonce": evaluation_data["nonce"],
            "repo_url": repo.html_url,
            "commit_sha": commit_sha,
            "pages_url": pages_url,
        }
        try:
            res = requests.post(evaluation_data["evaluation_url"], json=payload, timeout=10)
            print(f"Evaluation callback → {res.status_code}")
        except Exception as e:
            print(f"Evaluation callback failed: {e}")

    return repo.html_url, commit_sha, pages_url
