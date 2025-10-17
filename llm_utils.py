import os
from openai import OpenAI


def get_llm_client():
    base_url = os.getenv("OPENAI_BASE_URL", "https://aipipe.org/openai/v1")
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("AIPIPE_TOKEN")
    if not api_key:
        raise RuntimeError("AIPIPE_TOKEN or OPENAI_API_KEY not set")
    return OpenAI(base_url=base_url, api_key=api_key)


def summarize_attachments(attachments):
    """
    Creates a natural-language summary for the model to understand attachments.
    """
    if not attachments:
        return "No attachments were provided."
    desc = []
    for a in attachments:
        url = a.get("url", "")
        name = a.get("name", "unknown")
        if "image" in url:
            desc.append(f"- Image file: {name} (type: image, to be displayed or used for demo)")
        elif "text/csv" in url:
            desc.append(f"- CSV file: {name} (data file to read or process)")
        elif "text/markdown" in url:
            desc.append(f"- Markdown file: {name} (text content to render)")
        elif "application/json" in url:
            desc.append(f"- JSON file: {name} (data config or conversion rates)")
        else:
            desc.append(f"- File: {name} (type inferred from brief)")
    return "\n".join(desc)


def generate_files_from_brief(brief: str, attachments=None) -> dict:
    """
    Generate app files dynamically based on the given brief and attachments.
    Handles IITM-style requests with embedded data URIs.
    """
    attachments = attachments or []
    client = get_llm_client()

    attachment_summary = summarize_attachments(attachments)

    system_prompt = f"""
    You are an autonomous web app generator for IITM’s LLM Code Deployment platform.

    Your task:
    - Read the 'brief' describing what the app must do.
    - Review the attachments (summarized below).
    - Generate working static web app files (HTML, JS, CSS).

    Attachment Summary:
    {attachment_summary}

    Rules:
    - Output must be plain text (no code fences, no markdown formatting).
    - Write valid, minimal HTML5 with <html>, <head>, and <body>.
    - Include external libraries (Bootstrap, marked.js, highlight.js, etc.) from CDN links only.
    - Match element IDs and behavior exactly as described in the brief.
    - If the brief mentions an attachment, use its data URL directly in your HTML or JavaScript.
    - If data is to be fetched (e.g., CSV or JSON), use 'fetch()' with the data URI.
    - If an image is attached, show it by default in an <img> element.
    - Always produce functional code that would pass automated tests.
    - No comments or explanations — just clean code.
    """

    user_prompt = f"""
    Task brief:
    {brief}

    Generate the required web application based on the above brief and attachments.
    Return only the contents of index.html as plain text.
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

    # Safety cleanup for stray markdown formatting
    if html_code.startswith("```"):
        html_code = html_code.strip("`").replace("html", "", 1).strip()

    return {
        "index.html": html_code,
        "README.md": f"# Auto-generated App\n\n**Brief:** {brief}\n\nAttachments:\n{attachment_summary}\n\nGenerated automatically for IITM LLM Code Deployment.",
        "LICENSE": "MIT License\n\nCopyright (c) 2025",
    }
