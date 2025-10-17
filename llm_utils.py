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
        name = a.get("name", "unknown")
        mime = a.get("type", "unknown")
        if "image" in mime:
            desc.append(f"- Image file: {name}")
        elif "csv" in mime:
            desc.append(f"- CSV data file: {name}")
        elif "markdown" in mime:
            desc.append(f"- Markdown file: {name}")
        else:
            desc.append(f"- File: {name} ({mime})")
    return "\n".join(desc)


def generate_files_from_brief(brief: str, attachments=None) -> dict:
    attachments = attachments or []
    client = get_llm_client()
    summary = summarize_attachments(attachments)

    system_prompt = f"""
You are an autonomous web app generator for IITM’s LLM Code Deployment platform.
Read the 'brief', review attachments, and generate functional web app files.
Rules:
- Output plain HTML/JS/CSS only (no markdown or code fences)
- Use Bootstrap or marked.js via CDN
- Ensure <html>, <head>, <body> tags are valid
- Must render directly in a browser
"""

    user_prompt = f"""
Task Brief:
{brief}

Attachments Summary:
{summary}

Return a single valid index.html file content only.
"""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_prompt.strip()},
            {"role": "user", "content": user_prompt.strip()},
        ],
        temperature=0.2,
    )

    html_code = response.choices[0].message.content.strip()
    if html_code.startswith("```"):
        html_code = html_code.strip("`").replace("html", "", 1).strip()

    return {
        "index.html": html_code,
        "README.md": f"# Auto-generated Web App\n\n**Brief:** {brief}\n\nAttachments:\n{summary}",
    }
