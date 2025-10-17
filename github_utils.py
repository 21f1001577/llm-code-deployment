import os
import subprocess
import tempfile
import time
import requests
from github import Github, GithubException


def create_and_push_repo(repo_name, files, evaluation_data=None):
    """Create or reuse a GitHub repo, push files, enable Pages, and notify evaluation endpoint."""
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        raise RuntimeError("GITHUB_TOKEN not set")

    # Authenticate user
    user = Github(token).get_user()
    print(f"🔐 Authenticated as: {user.login}")

    # Try creating or reusing repo
    try:
        repo = user.create_repo(
            repo_name,
            description="Auto-generated repo for IITM LLM Deployment",
            private=False,
        )
        print(f"✅ Created new repo: {repo.html_url}")
    except GithubException as e:
        if e.status == 422 and "name already exists" in str(e.data).lower():
            repo = user.get_repo(repo_name)
            print(f"♻️ Repo '{repo_name}' already exists — reusing it.")
        else:
            print(f"❌ Repo creation failed: {e.data}")
            return None, None, None

    # Prepare workflow for GitHub Pages
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

    # --- Write files to temp dir and push ---
    try:
        with tempfile.TemporaryDirectory() as tmp:
            # Redirect HOME to prevent permission errors in Hugging Face
            os.environ["HOME"] = tmp

            # Write all generated files
            for name, content in files.items():
                file_path = os.path.join(tmp, name)
                os.makedirs(os.path.dirname(file_path), exist_ok=True)
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(content)

            subprocess.check_call(["git", "init"], cwd=tmp)

            # Configure local git identity (sandbox safe)
            user_login = user.login
            user_email = f"{user_login}@users.noreply.github.com"
            subprocess.check_call(["git", "config", "--local", "user.name", user_login], cwd=tmp)
            subprocess.check_call(["git", "config", "--local", "user.email", user_email], cwd=tmp)
            print(f"👤 Configured local git identity: {user_login} <{user_email}>")

            # Commit + push
            subprocess.check_call(["git", "add", "."], cwd=tmp)
            subprocess.check_call(["git", "commit", "-m", "Automated deployment"], cwd=tmp)
            subprocess.check_call(["git", "branch", "-M", "main"], cwd=tmp)

            push_url = f"https://{token}@github.com/{user.login}/{repo_name}.git"
            subprocess.check_call(["git", "remote", "add", "origin", push_url], cwd=tmp)
            subprocess.check_call(["git", "push", "-u", "origin", "main", "--force"], cwd=tmp)

            commit_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=tmp).decode().strip()
            print(f"✅ Successfully pushed commit {commit_sha} to {repo.html_url}")

    except subprocess.CalledProcessError as e:
        print(f"❌ Git subprocess failed: {e}")
        return None, None, None
    except Exception as e:
        print(f"❌ Unexpected git push error: {e}")
        return None, None, None

    # --- Enable GitHub Pages via API ---
    pages_url = f"https://{user.login}.github.io/{repo_name}/"
    api_url = f"https://api.github.com/repos/{user.login}/{repo_name}/pages"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    # Try POST (create) instead of PUT (update)
    for attempt in range(3):
        r = requests.post(api_url, headers=headers, json={"source": {"branch": "main", "path": "/"}}, timeout=15)
        if r.status_code in (201, 204):
            print(f"✅ Pages enabled successfully (attempt {attempt + 1})")
            break
        elif r.status_code == 409:
            print(f"⚠️ Pages already exists (409) — continuing.")
            break
        else:
            print(f"Attempt {attempt + 1}: Pages enablement failed ({r.status_code}) — {r.text}")
            time.sleep(5)
    else:
        print("❌ Could not enable GitHub Pages after 3 attempts.")

    # --- Notify evaluation server if applicable ---
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
        try:
            res = requests.post(evaluation_data["evaluation_url"], json=payload, timeout=10)
            print(f"📨 Evaluation POST → {res.status_code}")
        except Exception as e:
            print(f"⚠️ Evaluation callback failed: {e}")

    print(f"✅ Repo ready: {repo.html_url}")
    print(f"🔗 Pages URL: {pages_url}")
    return repo.html_url, commit_sha, pages_url
