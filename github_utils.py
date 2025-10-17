import os
import subprocess
import tempfile
import time
import requests
from github import Github, GithubException


def create_and_push_repo(repo_name, files, evaluation_data=None):
    """Create or reuse a GitHub repo, push files, enable Pages, and post callback."""
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
        print(f"Warning: Git identity config failed: {git_cfg_err}")

    # Create or reuse repo
    try:
        repo = user.create_repo(repo_name, description="Auto-generated repo for IITM Deployment", private=False)
        print(f"Repo created: {repo.html_url}")
    except GithubException as e:
        if e.status == 422 and "name already exists" in str(e.data).lower():
            repo = user.get_repo(repo_name)
            print(f"♻️ Repo '{repo_name}' already exists — reusing it.")
        else:
            print(f"Repo creation failed: {e.data}")
            return None, None, None

    # Workflow content
    workflow = """name: Deploy Pages
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
    files[".github/workflows/pages.yml"] = workflow

    try:
        with tempfile.TemporaryDirectory() as tmp:
            for name, content in files.items():
                path = os.path.join(tmp, name)
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "w") as f:
                    f.write(content)

            subprocess.check_call(["git", "init"], cwd=tmp)
            subprocess.check_call(["git", "config", "user.name", user_login], cwd=tmp)
            subprocess.check_call(["git", "config", "user.email", user_email], cwd=tmp)
            subprocess.check_call(["git", "add", "."], cwd=tmp)
            subprocess.check_call(["git", "commit", "-m", "Automated deployment"], cwd=tmp)
            subprocess.check_call(["git", "branch", "-M", "main"], cwd=tmp)

            push_url = f"https://{token}@github.com/{user_login}/{repo_name}.git"
            subprocess.check_call(["git", "remote", "add", "origin", push_url], cwd=tmp)
            subprocess.check_call(["git", "push", "-u", "origin", "main", "--force"], cwd=tmp)

            commit_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=tmp).decode().strip()
            print(f"✅ Successfully pushed commit {commit_sha} to {repo.html_url}")

    except subprocess.CalledProcessError as e:
        print(f"❌ Git error: {e}")
        return None, None, None

    pages_url = f"https://{user_login}.github.io/{repo_name}/"
    try:
        api = f"https://api.github.com/repos/{user_login}/{repo_name}/pages"
        headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github+json"}
        payload = {"source": {"branch": "main", "path": "/"}}
        r = requests.put(api, headers=headers, json=payload)
        if r.status_code in (201, 204):
            print("✅ GitHub Pages enabled successfully.")
        elif r.status_code == 404:
            print("ℹ️ Pages API not ready (expected on first run).")
        else:
            print(f"⚠️ Unexpected Pages API response {r.status_code}: {r.text}")
    except Exception as e:
        print(f"⚠️ Skipping Pages API: {e}")

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
            print(f"📨 Evaluation POST → {res.status_code}")
        except Exception as e:
            print(f"⚠️ Evaluation POST failed: {e}")

    print(f"✅ Repo ready: {repo.html_url}")
    print(f"🔗 Pages: {pages_url}")
    return repo.html_url, commit_sha, pages_url
