import sqlite3

DB_PATH = "./tasks.db"


def query_all_tasks():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "SELECT id, email, task, round, nonce, status, created_at FROM tasks ORDER BY created_at DESC"
    )
    rows = cur.fetchall()
    conn.close()
    return rows
