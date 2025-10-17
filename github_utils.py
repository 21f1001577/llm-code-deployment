import os, subprocess, tempfile, time, requests
from github import Github, GithubException


def create_and_push_repo(repo_name, files, evaluation_data=None):
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        raise RuntimeError("GITHUB_TOKEN not set")

    gh = Github(token)
    user = gh.get_user()
    print(f"🔐 Authenticated as: {user.login}")

    # Local git identity
    user_email = f"{user.login}@users.noreply.github.com"

    # --- Create or reuse repo ---
    try:
        repo = user.create_repo(repo_name, private=False, description="Auto-generated for IITM LLM Deployment")
        print(f"📁 Created new repo: {repo.html_url}")
    except GithubException as e:
        if e.status == 422:
            repo = user.get_repo(repo_name)
            print(f"♻️ Repo '{repo_name}' already exists — reusing it.")
        else:
            raise

    # --- Write workflow + files ---
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

    # --- Git push process ---
    with tempfile.TemporaryDirectory() as tmp:
        for name, content in files.items():
            path = os.path.join(tmp, name)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w") as f:
                f.write(content)

        subprocess.run(["git", "init"], cwd=tmp, check=True)
        subprocess.run(["git", "config", "user.name", user.login], cwd=tmp)
        subprocess.run(["git", "config", "user.email", user_email], cwd=tmp)
        subprocess.run(["git", "add", "."], cwd=tmp)
        subprocess.run(["git", "commit", "-m", "Automated deployment"], cwd=tmp)
        subprocess.run(["git", "branch", "-M", "main"], cwd=tmp)

        push_url = f"https://{token}@github.com/{user.login}/{repo_name}.git"
        subprocess.run(["git", "remote", "add", "origin", push_url], cwd=tmp)
        subprocess.run(["git", "push", "-u", "origin", "main", "--force"], cwd=tmp)

        commit_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=tmp).decode().strip()

    print(f"✅ Successfully pushed to {repo.html_url}")
    return repo.html_url, commit_sha, f"https://{user.login}.github.io/{repo_name}/"
