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

    gh = Github(token)
    user = gh.get_user()
    print(f"Authenticated as: {user.login}")

    # Create or reuse repo
    try:
        if update_existing:
            repo = user.get_repo(repo_name)
            print(f"♻️ Reusing existing repo: {repo.html_url}")
        else:
            repo = user.create_repo(repo_name, description="Auto-generated repo for IITM LLM Deployment", private=False)
            print(f"🆕 Created new repo: {repo.html_url}")
            time.sleep(8)
    except GithubException as e:
        if e.status == 422 and "name already exists" in str(e.data).lower():
            repo = user.get_repo(repo_name)
            print(f"♻️ Repo '{repo_name}' already exists — reusing.")
        else:
            raise

    # Pages workflow (verified working config)
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

    # Push files
    with tempfile.TemporaryDirectory() as tmpdir:
        for name, content in files.items():
            path = os.path.join(tmpdir, name)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
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
        print(f"✅ Pushed commit {commit_sha} to {repo.html_url}")

    # Wait for Pages API to exist
    pages_api = f"https://api.github.com/repos/{user.login}/{repo_name}/pages"
    headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github+json"}

    for i in range(8):
        r = requests.get(pages_api, headers=headers)
        if r.status_code == 200:
            print("✅ Pages site object ready.")
            break
        print(f"⏳ Waiting for Pages site registration ({r.status_code})...")
        time.sleep(5)
    else:
        print("⚠️ Pages site not ready yet — continuing anyway.")

    pages_url = f"https://{user.login}.github.io/{repo_name}/"

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
            print(f"⚠️ Evaluation callback failed: {e}")

    print(f"✅ Repo ready: {repo.html_url}")
    print(f"🔗 Pages: {pages_url}")
    return repo.html_url, commit_sha, pages_url
