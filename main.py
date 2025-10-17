from dotenv import load_dotenv
load_dotenv()
from fastapi import FastAPI, BackgroundTasks, HTTPException
from pydantic import BaseModel
import os
import hashlib
import uuid
from helpers import hash_secret, decode_data_uri
from github_utils import create_and_push_repo
from llm_utils import generate_files_from_brief



import sqlite3
import json

load_dotenv()

app = FastAPI()

STORED_SECRET_HASH = os.environ.get("STORED_SECRET_HASH")
OWNER_GITHUB = os.environ.get("GITHUB_USER")

# Simple SQLite logger (file: tasks.db)
db_path = os.environ.get("DB_PATH", "./tasks.db")

# If directory isn't writable (e.g., Hugging Face /app/), use /data
try:
    os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
    test_file = os.path.join(os.path.dirname(db_path) or ".", ".db_write_test")
    with open(test_file, "w") as f:
        f.write("")
    os.remove(test_file)
except (OSError, IOError):
    db_path = "/data/tasks.db"
    os.makedirs("/data", exist_ok=True)

DB_PATH = db_path


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


@app.post("/api-endpoint")
async def receive_task(req: TaskRequest, background_tasks: BackgroundTasks):
    # Verify secret
    if STORED_SECRET_HASH is None:
        raise HTTPException(status_code=500, detail="Server secret not configured")

    incoming_hash = hash_secret(req.secret)
    if incoming_hash != STORED_SECRET_HASH:
        raise HTTPException(status_code=403, detail="Invalid secret")

    # Store task in DB
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO tasks (email, task, round, nonce, secret_hash, brief, evaluation_url, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (req.email, req.task, req.round, req.nonce, incoming_hash, req.brief, req.evaluation_url, "received"),
    )
    conn.commit()
    conn.close()

    # Kick off background worker to create repo and push
    background_tasks.add_task(process_task, req.dict())

    return {"status": "accepted", "task": req.task, "round": req.round, "nonce": req.nonce}


def process_task(data: dict):
    task = data["task"]
    nonce = data["nonce"]
    short = nonce.replace("-", "")[:8]
    repo_name = f"{task}-{short}"

    try:
        # Generate files using the LLM
        from llm_utils import generate_files_from_brief
        print(f"Generating files for task: {task}")
        files = generate_files_from_brief(data["brief"])

        # Add MIT License to ensure evaluation passes
        files["LICENSE"] = get_mit_license_text()

    except Exception as e:
        print(f"LLM generation failed: {e}")
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute(
            "UPDATE tasks SET status=? WHERE nonce=?",
            (f"failed: LLM error: {e}", data["nonce"]),
        )
        conn.commit()
        conn.close()
        return

    # Create and push repo
    try:
        repo_url, commit_sha, pages_url = create_and_push_repo(
            repo_name,
            files,
            evaluation_data={
                "email": data["email"],
                "task": data["task"],
                "round": data["round"],
                "nonce": data["nonce"],
                "evaluation_url": data["evaluation_url"],
            },
        )
    except Exception as e:
        print(f"Background task failed: {e}")
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute(
            "UPDATE tasks SET status=? WHERE nonce=?",
            (f"failed: {str(e)}", data["nonce"]),
        )
        conn.commit()
        conn.close()
        return

    # Mark success
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "UPDATE tasks SET status=? WHERE nonce=?",
        (f"completed: {repo_url}", data["nonce"]),
    )
    conn.commit()
    conn.close()
    print(f"Task {data['task']} marked as completed: {repo_url}")

    # TODO: post to evaluation_url in Phase 3



def get_mit_license_text():
    return """MIT License

Copyright (c) 2025

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:
..."""
