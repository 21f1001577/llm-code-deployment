import os
import subprocess
import tempfile
import time
import requests
from github import Github, GithubException


def create_and_push_repo(repo_name, files, evaluation_data=None):
    """Create or reuse a GitHub repo, push initial files, enable Pages via Actions, and notify evaluation URL."""
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        raise RuntimeError("GITHUB_TOKEN not set")

    gh = Github(token)
    user = gh.get_user()
    print(f"Authenticated as: {user.login}")

    # Configure local Git identity
    user_email = f"{user.login}@users.noreply.github.com"
    subprocess.run(["git", "config", "--global", "user.name", user.login], check=False)
    subprocess.run(["git", "config", "--global", "user.email", user_email], check=False)

    # Try to create or fetch the repo
    try:
        repo = user.create_repo(
            repo_name,
            description="Auto-generated repo for IITM LLM Code Deployment",
            private=False,
            auto_init=False,
        )
        print(f"✅ Created new repo: {repo.html_url}")
    except GithubException as e:
        if e.status == 422 and "name already exists" in str(e.data).lower():
            print(f"♻️ Repo '{repo_name}' already exists — reusing it.")
            repo = user.get_repo(repo_name)
        else:
            raise

    # --- Add workflow ---
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

    # --- Write and push all files ---
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            for name, content in files.items():
                full_path = os.path.join(tmpdir, name)
                os.makedirs(os.path.dirname(full_path), exist_ok=True)
                with open(full_path, "w") as f:
                    f.write(content)

            subprocess.check_call(["git", "init"], cwd=tmpdir)
            subprocess.check_call(["git", "add", "."], cwd=tmpdir)
            subprocess.check_call(["git", "commit", "-m", "Automated deployment"], cwd=tmpdir)
            subprocess.check_call(["git", "branch", "-M", "main"], cwd=tmpdir)

            push_url = f"https://{token}@github.com/{user.login}/{repo_name}.git"
            subprocess.check_call(["git", "remote", "add", "origin", push_url], cwd=tmpdir)
            subprocess.check_call(["git", "push", "-u", "origin", "main", "--force"], cwd=tmpdir)

            commit_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=tmpdir).decode().strip()
    except subprocess.CalledProcessError as e:
        print(f"Git failed: {e}")
        return None, None, None

    # --- Enable Pages via API ---
    pages_api = f"https://api.github.com/repos/{user.login}/{repo_name}/pages"
    headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github+json"}
    payload = {"source": {"branch": "main", "path": "/"}}

    time.sleep(5)  # wait for branch registration
    r = requests.put(pages_api, headers=headers, json=payload)
    if r.status_code in (201, 204):
        print("✅ GitHub Pages enabled successfully.")
    elif r.status_code == 409:
        print("⚠️ Pages already enabled.")
    else:
        print(f"⚠️ Pages API returned {r.status_code}: {r.text}")

    pages_url = f"https://{user.login}.github.io/{repo_name}/"

    # --- Post back to evaluation_url ---
    if evaluation_data and evaluation_data.get("evaluation_url"):
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
            resp = requests.post(evaluation_data["evaluation_url"], json=payload, timeout=10)
            print(f"📨 Evaluation POST → {resp.status_code}")
        except Exception as e:
            print(f"⚠️ Evaluation callback failed: {e}")

    return repo.html_url, commit_sha, pages_url
