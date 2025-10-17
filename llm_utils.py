import os
from openai import OpenAI


def get_llm_client():
    base_url = os.getenv("OPENAI_BASE_URL", "https://aipipe.org/openai/v1")
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("AIPIPE_TOKEN")
    if not api_key:
        raise RuntimeError("AIPIPE_TOKEN or OPENAI_API_KEY not set")
    return OpenAI(base_url=base_url, api_key=api_key)


def summarize_attachments(attachments):
    if not attachments:
        return "No attachments were provided."
    desc = []
    for a in attachments:
        url = a.get("url", "")
        name = a.get("name", "unknown")
        if "image" in url:
            desc.append(f"- Image: {name}")
        elif "csv" in url:
            desc.append(f"- CSV data file: {name}")
        elif "markdown" in url:
            desc.append(f"- Markdown text: {name}")
        elif "json" in url:
            desc.append(f"- JSON config: {name}")
        else:
            desc.append(f"- File: {name}")
    return "\n".join(desc)


def generate_files_from_brief(brief: str, attachments=None) -> dict:
    attachments = attachments or []
    client = get_llm_client()
    attachment_summary = summarize_attachments(attachments)

    system_prompt = f"""
You are an autonomous web app generator for IITM’s LLM Code Deployment platform.

- Read the 'brief' and attachments summary.
- Generate working static web app files (HTML, JS, CSS).
- Use only CDN libraries (Bootstrap, highlight.js, marked.js, etc.).
- Use provided data URIs directly where needed.
- No markdown fences or extra text — plain code only.
"""

    user_prompt = f"""
Task Brief:
{brief}

Attachments Summary:
{attachment_summary}

Generate a complete index.html as plain HTML5 text.
"""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_prompt.strip()},
            {"role": "user", "content": user_prompt.strip()},
        ],
        temperature=0.25,
    )

    html_code = response.choices[0].message.content.strip()

    if html_code.startswith("```"):
        html_code = html_code.strip("`").replace("html", "", 1).strip()

    return {
        "index.html": html_code,
        "README.md": f"# Auto-generated App\n\n**Brief:** {brief}\n\nAttachments:\n{attachment_summary}\n\nGenerated automatically for IITM LLM Code Deployment.",
        "LICENSE": "MIT License\n\nCopyright (c) 2025",
    }
