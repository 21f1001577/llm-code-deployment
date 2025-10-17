import os, requests
from openai import OpenAI


def get_llm_client():
    base_url = os.getenv("OPENAI_BASE_URL", "https://aipipe.org/openai/v1")
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("AIPIPE_TOKEN")
    return OpenAI(base_url=base_url, api_key=api_key)


def summarize_attachments(attachments):
    return "\n".join([f"- {a.get('name')}: {a.get('url')[:40]}..." for a in attachments]) if attachments else "No attachments."


def get_existing_html(user, repo_name):
    try:
        r = requests.get(f"https://raw.githubusercontent.com/{user}/{repo_name}/main/index.html", timeout=10)
        if r.status_code == 200:
            return r.text
    except Exception:
        pass
    return ""


def generate_files_from_brief(brief: str, attachments=None, round_number=1, user=None, repo_name=None):
    attachments = attachments or []
    client = get_llm_client()
    attachment_summary = summarize_attachments(attachments)

    system_prompt = (
        "You are an autonomous web app generator for IITM’s LLM Code Deployment platform.\n"
        "Generate minimal HTML5+JS+CSS web apps for given briefs. Attachments are provided as data URIs.\n"
        "Use them directly inside <script> or <img> tags as needed. Do not print markdown or code fences.\n"
    )

    existing_html = get_existing_html(user, repo_name) if round_number == 2 else ""
    user_prompt = f"""
Round {round_number} Brief:
{brief}

Existing HTML (if any):
{existing_html[:2000]}

Attachments:
{attachment_summary}

Return only HTML for index.html.
"""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0.25,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )

    html = response.choices[0].message.content.strip()
    if html.startswith("```"):
        html = html.strip("`").replace("html", "").strip()

    return {
        "index.html": html,
        "README.md": f"# Auto-generated App\n\n**Brief:** {brief}\n\nRound: {round_number}\n\nAttachments:\n{attachment_summary}",
        "LICENSE": "MIT License\n\nCopyright (c) 2025",
    }
