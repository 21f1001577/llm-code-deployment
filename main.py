from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, BackgroundTasks, HTTPException
from pydantic import BaseModel
import os, sqlite3, time, requests
from helpers import hash_secret
from github_utils import create_and_push_repo
from llm_utils import generate_files_from_brief

# === CONFIG ===
STORED_SECRET_HASH = os.environ.get("STORED_SECRET_HASH")
OWNER_GITHUB = os.environ.get("GITHUB_USER")
DB_PATH = os.environ.get("DB_PATH", "./tasks.db")

# Ensure DB writable (Hugging Face-safe)
try:
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    with open(os.path.join(os.path.dirname(DB_PATH) or ".", ".db_write_test"), "w") as f:
        f.write("")
except (OSError, IOError):
    DB_PATH = "/tmp/tasks.db"
    os.makedirs("/tmp", exist_ok=True)

app = FastAPI(title="IITM LLM Code Deployment API")

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY,
            email TEXT,
            task TEXT,
            round INTEGER,
            nonce TEXT,
            secret_hash TEXT,
            brief TEXT,
            evaluation_url TEXT,
            status TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()
init_db()


class TaskRequest(BaseModel):
    email: str
    secret: str
    task: str
    round: int
    nonce: str
    brief: str = ""
    checks: list = []
    evaluation_url: str = None
    attachments: list = []


@app.post("/api-endpoint")
async def receive_task(req: TaskRequest, background_tasks: BackgroundTasks):
    if not STORED_SECRET_HASH:
        raise HTTPException(status_code=500, detail="Server secret not configured")
    if hash_secret(req.secret) != STORED_SECRET_HASH:
        raise HTTPException(status_code=403, detail="Invalid secret")

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO tasks (email, task, round, nonce, secret_hash, brief, evaluation_url, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (req.email, req.task, req.round, req.nonce, STORED_SECRET_HASH, req.brief, req.evaluation_url, "received"),
    )
    conn.commit()
    conn.close()

    background_tasks.add_task(process_task, req.dict())
    return {"status": "accepted", "task": req.task, "round": req.round, "nonce": req.nonce}


def process_task(data: dict):
    task = data["task"]
    nonce = data["nonce"]
    round_number = data.get("round", 1)
    short = nonce.replace("-", "")[:8]
    repo_name = f"{task}-{short}"

    print(f"Processing {task} (Round {round_number})")

    try:
        files = generate_files_from_brief(
            brief=data["brief"],
            attachments=data.get("attachments", []),
            round_number=round_number,
            user=OWNER_GITHUB,
            repo_name=repo_name,
        )
        files["LICENSE"] = get_mit_license_text()

        repo_url, commit_sha, pages_url = create_and_push_repo(
            repo_name, files,
            evaluation_data={
                "email": data["email"],
                "task": task,
                "round": round_number,
                "nonce": nonce,
                "evaluation_url": data.get("evaluation_url"),
            },
        )

        post_to_evaluation_url(data, repo_url, commit_sha, pages_url)

        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute(
            "UPDATE tasks SET status=? WHERE nonce=?",
            (f"completed: {task} round {round_number}", nonce),
        )
        conn.commit()
        conn.close()
        print(f"✅ Task {task} (round {round_number}) completed successfully")
        print(f"🔗 Pages URL: {pages_url}")

    except Exception as e:
        print(f"❌ Process failed for {task} (round {round_number}): {e}")
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("UPDATE tasks SET status=? WHERE nonce=?", (f"failed: {str(e)}", nonce))
        conn.commit()
        conn.close()


def post_to_evaluation_url(data, repo_url, commit_sha, pages_url):
    """POST to evaluation_url with exponential backoff (per IITM spec)."""
    if not data.get("evaluation_url"):
        print("⚠️ No evaluation_url provided, skipping callback.")
        return

    payload = {
        "email": data["email"],
        "task": data["task"],
        "round": data["round"],
        "nonce": data["nonce"],
        "repo_url": repo_url,
        "commit_sha": commit_sha,
        "pages_url": pages_url,
    }

    for delay in [1, 2, 4, 8]:
        try:
            res = requests.post(data["evaluation_url"], json=payload, timeout=10)
            print(f"📨 Evaluation POST → {res.status_code}")
            if res.status_code == 200:
                print("✅ Evaluation server acknowledged successfully.")
                return
        except Exception as e:
            print(f"⚠️ Evaluation POST failed (retrying in {delay}s): {e}")
        time.sleep(delay)
    print("❌ Could not reach evaluation_url after multiple retries.")


def get_mit_license_text():
    return """MIT License

Copyright (c) 2025

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
"""
