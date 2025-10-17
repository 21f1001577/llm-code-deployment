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
            desc.append(f"- Image file: {name}")
        elif "csv" in url:
            desc.append(f"- CSV file: {name}")
        elif "markdown" in url:
            desc.append(f"- Markdown file: {name}")
        elif "json" in url:
            desc.append(f"- JSON file: {name}")
        else:
            desc.append(f"- File: {name}")
    return "\n".join(desc)


def generate_files_from_brief(brief: str, attachments=None) -> dict:
    attachments = attachments or []
    client = get_llm_client()
    attachment_summary = summarize_attachments(attachments)

    system_prompt = f"""
You are an autonomous web app generator for IITM’s LLM Code Deployment platform.

Instructions:
- Read the brief carefully.
- Use attachments as described.
- Produce a single-page web app with valid HTML, JS, and CSS.
- Use Bootstrap or CDNs as needed.
- No markdown formatting or extra commentary.
- Output only HTML (plain text).
"""

    user_prompt = f"Brief:\n{brief}\n\nAttachments:\n{attachment_summary}\n\nGenerate the HTML."

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
        html_code = html_code.strip("`").replace("html", "").strip()

    return {
        "index.html": html_code,
        "README.md": f"# Auto-generated App\n\n**Brief:** {brief}\n\nAttachments:\n{attachment_summary}\n",
        "LICENSE": "MIT License\n\nCopyright (c) 2025",
    }
