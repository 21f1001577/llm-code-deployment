import os
import subprocess
import tempfile
import time
import requests
from github import Github, GithubException


def create_and_push_repo(repo_name, files, evaluation_data=None):
    """Create or reuse a GitHub repo, push initial files, enable Pages via Actions, and notify evaluation URL."""
    token = os.getenv("GITHUB_TOKEN")
    user = Github(token).get_user()
    print(f"Authenticated as: {user.login}")
    if not token:
        raise RuntimeError("GITHUB_TOKEN not set")

    try:
        user_login = user.login
        user_email = f"{user_login}@users.noreply.github.com"
        subprocess.run(["git", "config", "user.name", user_login], check=False)
        subprocess.run(["git", "config", "user.email", user_email], check=False)
        print(f"Configured local git identity: {user_login} <{user_email}>")
    except Exception as git_cfg_err:
        print(f"Warning: Failed to configure local git identity - {git_cfg_err}")

    repo = None
    try:
        # Try to create new repo
        repo = user.create_repo(
            repo_name,
            description="Auto-generated repo for IITM LLM Deployment",
            private=False,
        )
        print(f"Repo created: {repo.html_url}")
    except GithubException as e:
        # Gracefully handle repo already existing
        if e.status == 422 and "name already exists" in str(e.data).lower():
            print(f"Repo '{repo_name}' already exists. Reusing existing repository.")
            try:
                repo = user.get_repo(repo_name)
            except Exception as inner_e:
                print(f"Failed to fetch existing repo: {inner_e}")
                return None, None, None
        else:
            print(f"Unexpected repo creation error: {e.data}")
            return None, None, None

    # --- Ensure GitHub Pages workflow file always exists ---
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
      - name: Checkout
        uses: actions/checkout@v4
      - name: Setup Pages
        uses: actions/configure-pages@v4
      - name: Upload artifact
        uses: actions/upload-pages-artifact@v3
        with:
          path: .
      - name: Deploy to GitHub Pages
        id: deployment
        uses: actions/deploy-pages@v4
"""
    files[".github/workflows/pages.yml"] = workflow_content

    # --- Write files to a temp directory and push to GitHub ---
    try:
        with tempfile.TemporaryDirectory() as tmp:
            for name, content in files.items():
                file_path = os.path.join(tmp, name)
                os.makedirs(os.path.dirname(file_path), exist_ok=True)
                with open(file_path, "w") as f:
                    f.write(content)

            subprocess.check_call(["git", "init"], cwd=tmp)
            subprocess.check_call(["git", "add", "."], cwd=tmp)
            subprocess.check_call(["git", "commit", "-m", "Initial commit by automation"], cwd=tmp)
            subprocess.check_call(["git", "branch", "-M", "main"], cwd=tmp)

            push_url = f"https://{token}@github.com/{user.login}/{repo_name}.git"
            subprocess.check_call(["git", "remote", "add", "origin", push_url], cwd=tmp)
            subprocess.check_call(["git", "push", "-u", "origin", "main", "--force"], cwd=tmp)

            commit_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=tmp).decode().strip()
    except subprocess.CalledProcessError as e:
        print(f"Git subprocess failed: {e}")
        return None, None, None
    except Exception as e:
        print(f"Unexpected push error: {e}")
        return None, None, None

    # --- Attempt GitHub Pages API (ignore all errors, log only) ---
    pages_url = f"https://{user.login}.github.io/{repo_name}/"
    try:
        pages_api = f"https://api.github.com/repos/{user.login}/{repo_name}/pages"
        headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github+json"}
        payload = {"source": {"branch": "main", "path": "/"}}

        r = requests.put(pages_api, headers=headers, json=payload)
        if r.status_code == 404:
            print("GitHub Pages API not available for user repos. Skipping automated enablement (expected).")
        elif r.status_code in (201, 204):
            print("GitHub Pages enabled successfully via API.")
        else:
            print(f"Unexpected Pages API response ({r.status_code}): {r.text}")
    except Exception as e:
        print(f"Skipping Pages API call due to error: {e}")

    print("Repo successfully pushed and workflow added. Marking task as completed.")

    # --- Evaluation callback ---
    if evaluation_data:
        payload = {
            "email": evaluation_data["email"],
            "task": evaluation_data["task"],
            "round": evaluation_data["round"],
            "nonce": evaluation_data["nonce"],
            "repo_url": repo.html_url if repo else "",
            "commit_sha": commit_sha if repo else "",
            "pages_url": pages_url,
        }
        for delay in [1, 2, 4, 8]:
            try:
                res = requests.post(evaluation_data["evaluation_url"], json=payload, timeout=10)
                print(f"Evaluation response: {res.status_code}")
                if res.status_code == 200:
                    break
            except Exception as e:
                print(f"Evaluation POST failed: {e}")
            time.sleep(delay)

    return repo.html_url if repo else "", commit_sha if repo else "", pages_url
