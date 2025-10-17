import os
import subprocess
import tempfile
import time
import requests
from github import Github, GithubException


def create_and_push_repo(repo_name, files, evaluation_data=None, update_existing=False):
    """Create or reuse a GitHub repo, push files, enable Pages, and notify evaluation URL."""

    token = os.getenv("GITHUB_TOKEN")
    if not token:
        raise RuntimeError("GITHUB_TOKEN not set")

    gh = Github(token)
    user = gh.get_user()
    print(f"Authenticated as: {user.login}")

    # === Create or reuse repository ===
    try:
        if update_existing:
            repo = user.get_repo(repo_name)
            print(f"♻️ Reusing existing repo: {repo.html_url}")
        else:
            repo = user.create_repo(
                repo_name,
                description="Auto-generated repo for IITM LLM Deployment",
                private=False,
            )
            print(f"🆕 Created new repo: {repo.html_url}")
            # GitHub Pages sometimes needs a delay before configuration
            time.sleep(5)
    except GithubException as e:
        if e.status == 422 and "name already exists" in str(e.data).lower():
            repo = user.get_repo(repo_name)
            print(f"♻️ Repo '{repo_name}' already exists — reusing it.")
        else:
            print(f"❌ Repo creation failed: {e.data}")
            return None, None, None

    # === Pre-enable Pages (critical for new repos) ===
    try:
        print("🔧 Pre-enabling GitHub Pages via API...")
        enable_payload = {"source": {"branch": "main", "path": "/"}}
        enable_url = f"https://api.github.com/repos/{user.login}/{repo_name}/pages"
        r = requests.put(enable_url, headers={"Authorization": f"token {token}"}, json=enable_payload)
        print(f"Pages pre-enable response: {r.status_code}")
    except Exception as e:
        print(f"⚠️ Failed to pre-enable Pages: {e}")

    # === Verified working workflow ===
    workflow_content = """name: Deploy Pages

on:
  push:
    branches: [ main ]

permissions:
  contents: write
  pages: write
  id-token: write
  actions: write

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
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Setup Pages
        uses: actions/configure-pages@v4
        with:
          enablement: true
          token: ${{ secrets.GITHUB_PAT }}

      - name: Upload artifact
        uses: actions/upload-pages-artifact@v3
        with:
          path: .

      - name: Deploy to GitHub Pages
        id: deployment
        uses: actions/deploy-pages@v4
        with:
          token: ${{ secrets.GITHUB_PAT }}
"""

    files[".github/workflows/pages.yml"] = workflow_content

    # === Write files to a temporary directory and push ===
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            for name, content in files.items():
                file_path = os.path.join(tmpdir, name)
                os.makedirs(os.path.dirname(file_path), exist_ok=True)
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(content)

            subprocess.check_call(["git", "init"], cwd=tmpdir)
            subprocess.check_call(["git", "config", "user.name", user.login], cwd=tmpdir)
            subprocess.check_call(["git", "config", "user.email", f"{user.login}@users.noreply.github.com"], cwd=tmpdir)
            subprocess.check_call(["git", "add", "."], cwd=tmpdir)
            subprocess.run(["git", "commit", "-m", "Automated deployment"], cwd=tmpdir, check=False)
            subprocess.check_call(["git", "branch", "-M", "main"], cwd=tmpdir)

            push_url = f"https://{token}@github.com/{user.login}/{repo_name}.git"
            subprocess.run(["git", "remote", "remove", "origin"], cwd=tmpdir, check=False)
            subprocess.check_call(["git", "remote", "add", "origin", push_url], cwd=tmpdir)
            subprocess.check_call(["git", "push", "-u", "origin", "main", "--force"], cwd=tmpdir)

            commit_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=tmpdir).decode().strip()
            print(f"✅ Successfully pushed commit {commit_sha} to {repo.html_url}")

    except subprocess.CalledProcessError as e:
        print(f"❌ Git subprocess failed: {e}")
        return None, None, None
    except Exception as e:
        print(f"❌ Unexpected Git push error: {e}")
        return None, None, None

    # === Wait for Pages API to be ready ===
    pages_url = f"https://{user.login}.github.io/{repo_name}/"
    pages_api = f"https://api.github.com/repos/{user.login}/{repo_name}/pages"
    headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github+json"}

    for attempt in range(8):
        r = requests.get(pages_api, headers=headers)
        if r.status_code == 200:
            print("✅ Pages site is ready.")
            break
        print(f"⏳ Waiting for Pages site (attempt {attempt + 1}/8)... status {r.status_code}")
        time.sleep(5)
    else:
        print("⚠️ Pages API did not become ready in time. The workflow should still deploy.")

    # === Callback to evaluation ===
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
            print(f"📨 Evaluation callback → {res.status_code}")
        except Exception as e:
            print(f"⚠️ Evaluation callback failed: {e}")

    print(f"✅ Repo ready: {repo.html_url}")
    print(f"🔗 Pages: {pages_url}")
    return repo.html_url, commit_sha, pages_url
