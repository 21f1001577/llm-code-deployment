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
            desc.append(f"- Image: {name} (display or analyze)")
        elif "text/csv" in url:
            desc.append(f"- CSV: {name} (data input)")
        elif "text/markdown" in url:
            desc.append(f"- Markdown: {name}")
        elif "application/json" in url:
            desc.append(f"- JSON: {name}")
        else:
            desc.append(f"- File: {name}")
    return "\n".join(desc)


def generate_files_from_brief(brief: str, attachments=None, round_number: int = 1) -> dict:
    """
    Generate or update app files based on IITM-style briefs.
    Round 1 → new app
    Round 2 → incremental improvement of previous version
    """
    attachments = attachments or []
    client = get_llm_client()
    attachment_summary = summarize_attachments(attachments)

    system_prompt = f"""
    You are an autonomous web app generator for IITM’s LLM Code Deployment system.
    Attachment summary:
    {attachment_summary}

    Rules:
    - Output plain HTML (no markdown, no code fences)
    - Use Bootstrap/marked.js/highlight.js from CDNs
    - Round 1: build new app
    - Round 2: refine or improve an existing app, keeping functionality consistent but cleaner or more complete
    - No comments or explanations
    """

    user_prompt = f"""
    Round: {round_number}
    Brief:
    {brief}

    Generate functional static web app code as index.html.
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
        "README.md": f"# Auto-generated App\n\n**Brief:** {brief}\n\nRound: {round_number}\n\nAttachments:\n{attachment_summary}",
    }
