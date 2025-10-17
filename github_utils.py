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

    # 1️⃣ Create or reuse repo
    try:
        repo = user.create_repo(
            repo_name,
            description="Auto-generated repo for IITM LLM Deployment",
            private=False,
        )
        print(f"Repo created: {repo.html_url}")
    except GithubException as e:
        if e.status == 422 and "name already exists" in str(e.data).lower():
            print(f"Repo '{repo_name}' already exists. Reusing it.")
            repo = user.get_repo(repo_name)
        else:
            print(f"Repo creation error: {e.data}")
            return None, None, None

    # 2️⃣ Pre-enable GitHub Pages environment
    try:
        headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github+json"}
        payload = {"source": {"branch": "main", "path": "/"}}
        pages_api = f"https://api.github.com/repos/{user.login}/{repo_name}/pages"
        r = requests.post(pages_api, headers=headers, json=payload)
        if r.status_code in (201, 204):
            print("✅ Pre-enabled GitHub Pages environment via API.")
        elif r.status_code == 409:
            print("ℹ️ Pages already enabled.")
        else:
            print(f"⚠️ Pages pre-enable response: {r.status_code} {r.text}")
    except Exception as e:
        print(f"⚠️ Skipping Pages pre-enable step: {e}")

    # 3️⃣ Add workflow
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

    # 4️⃣ Write and push to GitHub
    try:
        with tempfile.TemporaryDirectory() as tmp:
            print(f"Preparing repo in {tmp}")
            for name, content in files.items():
                file_path = os.path.join(tmp, name)
                os.makedirs(os.path.dirname(file_path), exist_ok=True)
                with open(file_path, "w") as f:
                    f.write(content)

            subprocess.run(["git", "init"], cwd=tmp, check=True)
            user_email = f"{user.login}@users.noreply.github.com"
            subprocess.run(["git", "config", "user.name", user.login], cwd=tmp, check=True)
            subprocess.run(["git", "config", "user.email", user_email], cwd=tmp, check=True)
            subprocess.run(["git", "branch", "-M", "main"], cwd=tmp, check=False)
            subprocess.run(["git", "add", "."], cwd=tmp, check=True)
            subprocess.run(["git", "commit", "-m", "Initial commit by automation"], cwd=tmp, check=True)

            push_url = f"https://{token}@github.com/{user.login}/{repo_name}.git"
            subprocess.run(["git", "remote", "add", "origin", push_url], cwd=tmp, check=True)
            subprocess.run(["git", "push", "-u", "origin", "main", "--force"], cwd=tmp, check=True)

            commit_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=tmp).decode().strip()

    except subprocess.CalledProcessError as e:
        print(f"❌ Git subprocess failed: {e}")
        return None, None, None

    # 5️⃣ Verify Pages deployment
    pages_url = f"https://{user.login}.github.io/{repo_name}/"
    print(f"📄 Expected Pages URL: {pages_url}")
    for i in range(10):
        try:
            res = requests.get(pages_url, timeout=5)
            if res.status_code == 200:
                print(f"✅ Pages is live: {pages_url}")
                break
        except Exception:
            pass
        time.sleep(5)
    else:
        print("⚠️ Pages not live yet, will rely on GitHub Actions to finish build.")

    # 6️⃣ Notify evaluation server
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
                print(f"📤 Evaluation callback status: {res.status_code}")
                if res.status_code == 200:
                    break
            except Exception as e:
                print(f"⚠️ Evaluation callback failed: {e}")
            time.sleep(delay)

    print("✅ Repo successfully pushed, workflow added, and callback sent.")
    return repo.html_url if repo else "", commit_sha if repo else "", pages_url
