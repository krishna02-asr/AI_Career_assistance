"""
ai_engine.py

The "brain" of the project. Every function here talks to the Groq API and
turns a resume + job description into specific, recruiter-style feedback.

Public functions (same names/returns as before, so app.py keeps working):
  - analyze_resume_vs_jd(resume_text, job_description) -> dict
  - generate_interview_questions(resume_text, job_description, num_questions) -> list[str]
  - chat_with_assistant(conversation_history, resume_text, job_description, user_message) -> str

New keys added to analyze_resume_vs_jd (optional to use in app.py):
  - section_scores : {"summary": int, "skills": int, "experience": int, "projects": int, "education": int}
  - top_fixes      : [{"issue", "resume_line", "fix", "before", "after"}]
  - strengths      : [str]
"""

import os
import re
import json
import time

from groq import Groq
from dotenv import load_dotenv

load_dotenv()  # local: reads GROQ_API_KEY from .env


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

def _get_api_key() -> str:
    """Local .env first, then Streamlit Cloud secrets."""
    key = os.getenv("GROQ_API_KEY")
    if key:
        return key
    try:
        import streamlit as st
        return st.secrets["GROQ_API_KEY"]
    except Exception:
        return ""


client = Groq(api_key=_get_api_key())

MODEL = "openai/gpt-oss-20b"

# Low temperature = stable, consistent feedback (less "creative AI waffle")
TEMP_ANALYSIS = 0.3
TEMP_QUESTIONS = 0.5
TEMP_CHAT = 0.5

MAX_RETRIES = 2
MAX_INPUT_CHARS = 12000  # protects against huge pastes


# ---------------------------------------------------------------------------
# Style rules shared by every prompt
# ---------------------------------------------------------------------------

STYLE_RULES = (
    "WRITING STYLE RULES (very important):\n"
    "- Write like a senior recruiter talking to a friend: simple, direct, plain words.\n"
    "- Be specific. Quote the candidate's actual resume lines when giving feedback.\n"
    "- Never use these words or phrases: leverage, delve, robust, comprehensive, "
    "seamless, cutting-edge, tapestry, testament, utilize, showcase, pivotal, "
    "\"in today's fast-paced world\", \"it is worth noting\", \"overall\", "
    "\"as an AI\", \"I hope this helps\", \"great question\".\n"
    "- Do not use em-dashes. Use commas or short sentences instead.\n"
    "- No filler intro or outro. Start with the useful point.\n"
    "- Never invent experience, numbers or skills the candidate does not have. "
    "If a metric is missing, tell them to add a real one, do not make one up.\n"
)

# Few-shot example so the model copies the tone and level of detail
FEW_SHOT_EXAMPLE = """
EXAMPLE OF GOOD FEEDBACK (copy this tone and specificity, not the content):
{
  "issue": "Bullet has no result",
  "resume_line": "Worked on backend APIs for the payments team",
  "fix": "Say what you built and what changed because of it. Add a real number if you have one.",
  "before": "Worked on backend APIs for the payments team",
  "after": "Built 6 REST APIs in Flask for the payments team, cutting average response time from 800ms to 480ms"
}
"""

BANNED_PATTERNS = [
    (r"\bas an ai( language model)?,?\s*", ""),
    (r"\bi hope this helps[.!]?\s*", ""),
    (r"\bgreat question[.!]?\s*", ""),
    (r"\bin today's fast-paced world,?\s*", ""),
    (r"\bit is worth noting that\s*", ""),
    (r"\bleverag(e|es|ed|ing)\b", "use"),
    (r"\butiliz(e|es|ed|ing)\b", "use"),
    (r"\bdelv(e|es|ed|ing)\b", "look"),
    (r"\brobust\b", "solid"),
    (r"\bcomprehensive\b", "complete"),
    (r"\bseamless(ly)?\b", "smooth"),
    (r"\bcutting-edge\b", "modern"),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_text(text: str) -> str:
    """Remove AI-sounding filler and punctuation habits from any string."""
    if not isinstance(text, str):
        return text

    cleaned = text
    for pattern, replacement in BANNED_PATTERNS:
        cleaned = re.sub(pattern, replacement, cleaned, flags=re.IGNORECASE)

    # em-dash / en-dash used as a pause -> comma
    cleaned = re.sub(r"\s*[—–]\s*", ", ", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()

    # Fix sentences that now start in lowercase after removals
    if cleaned and cleaned[0].islower():
        cleaned = cleaned[0].upper() + cleaned[1:]
    return cleaned


def _clean_structure(obj):
    """Apply _clean_text to every string inside a dict/list."""
    if isinstance(obj, str):
        return _clean_text(obj)
    if isinstance(obj, list):
        return [_clean_structure(i) for i in obj]
    if isinstance(obj, dict):
        return {k: _clean_structure(v) for k, v in obj.items()}
    return obj


def _trim(text: str) -> str:
    text = (text or "").strip()
    return text[:MAX_INPUT_CHARS]


def _extract_json(text: str) -> dict:
    """
    Pull a JSON object out of the model reply, even if it adds
    markdown fences or a stray sentence before/after.
    """
    cleaned = (text or "").strip()

    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start != -1 and end > start:
            return json.loads(cleaned[start:end + 1])
        raise


def _call_llm(messages: list, max_tokens: int, temperature: float) -> str:
    """One place for API calls, with retry on temporary failures."""
    last_error = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            response = client.chat.completions.create(
                model=MODEL,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            return response.choices[0].message.content or ""
        except Exception as e:  # network, rate limit, etc.
            last_error = e
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"AI service is not responding right now: {last_error}")


def _call_json(messages: list, max_tokens: int, temperature: float) -> dict:
    """Call the model and parse JSON. Retries if the JSON is broken."""
    last_error = None
    for _ in range(MAX_RETRIES + 1):
        raw = _call_llm(messages, max_tokens, temperature)
        try:
            return _extract_json(raw)
        except (json.JSONDecodeError, ValueError) as e:
            last_error = e
    raise RuntimeError(f"Could not read the AI response as JSON: {last_error}")


def _clamp(value, low=0, high=100, default=0) -> int:
    try:
        return max(low, min(high, int(round(float(value)))))
    except (TypeError, ValueError):
        return default


def _as_str_list(value) -> list:
    if not isinstance(value, list):
        return []
    return [str(v).strip() for v in value if str(v).strip()]


# ---------------------------------------------------------------------------
# 1. Resume vs Job Description
# ---------------------------------------------------------------------------

def analyze_resume_vs_jd(resume_text: str, job_description: str) -> dict:
    """
    Compares the resume against the job description.

    Returns a dict with:
      match_percentage, matching_skills, missing_skills, suggestions, summary,
      section_scores, top_fixes, strengths
    """

    system_prompt = (
        "You are a senior technical recruiter who has screened thousands of resumes. "
        "You compare a resume against a job description and give honest, specific feedback.\n\n"
        + STYLE_RULES + "\n"
        "SCORING GUIDE for match_percentage:\n"
        "- 80-100: meets almost all must-have skills with proof in experience/projects\n"
        "- 60-79: meets most must-haves, a few gaps\n"
        "- 40-59: partial fit, several important gaps\n"
        "- below 40: weak fit\n"
        "Only count a skill as matching if the resume actually shows it.\n\n"
        "Return exactly 3 to 5 items in top_fixes, most important first. "
        "Each resume_line must be copied from the resume text. "
        "The 'after' example must not contain made-up numbers; use placeholders "
        "like [X%] if the real number is unknown.\n"
        + FEW_SHOT_EXAMPLE + "\n"
        "Respond ONLY with valid JSON. No preamble, no markdown fences. "
        "Use exactly this schema:\n"
        "{\n"
        '  "match_percentage": <integer 0-100>,\n'
        '  "matching_skills": [<strings>],\n'
        '  "missing_skills": [<strings>],\n'
        '  "strengths": [<2-4 short strings, what already works>],\n'
        '  "section_scores": {"summary": <0-100>, "skills": <0-100>, '
        '"experience": <0-100>, "projects": <0-100>, "education": <0-100>},\n'
        '  "top_fixes": [{"issue": "<string>", "resume_line": "<copied from resume>", '
        '"fix": "<string>", "before": "<string>", "after": "<string>"}],\n'
        '  "summary": "<2-3 plain sentences: honest verdict and the one thing to fix first>"\n'
        "}"
    )

    user_message = (
        f"JOB DESCRIPTION:\n{_trim(job_description)}\n\n"
        f"CANDIDATE RESUME:\n{_trim(resume_text)}\n\n"
        "Analyze the fit and return the JSON exactly as specified."
    )

    data = _call_json(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        max_tokens=2500,
        temperature=TEMP_ANALYSIS,
    )

    data = _clean_structure(data)

    # ---- normalise so app.py never crashes on missing/odd values ----
    section_scores = data.get("section_scores") or {}
    clean_sections = {
        name: _clamp(section_scores.get(name))
        for name in ("summary", "skills", "experience", "projects", "education")
    }

    top_fixes = []
    for fix in data.get("top_fixes") or []:
        if isinstance(fix, dict):
            top_fixes.append({
                "issue": str(fix.get("issue", "")).strip(),
                "resume_line": str(fix.get("resume_line", "")).strip(),
                "fix": str(fix.get("fix", "")).strip(),
                "before": str(fix.get("before", "")).strip(),
                "after": str(fix.get("after", "")).strip(),
            })

    # Old app.py expects `suggestions` as a list of strings, keep it filled
    suggestions = _as_str_list(data.get("suggestions"))
    if not suggestions:
        suggestions = [
            f"{f['issue']}: {f['fix']}".strip(": ")
            for f in top_fixes if f["issue"] or f["fix"]
        ]

    return {
        "match_percentage": _clamp(data.get("match_percentage")),
        "matching_skills": _as_str_list(data.get("matching_skills")),
        "missing_skills": _as_str_list(data.get("missing_skills")),
        "strengths": _as_str_list(data.get("strengths")),
        "section_scores": clean_sections,
        "top_fixes": top_fixes,
        "suggestions": suggestions,
        "summary": str(data.get("summary", "")).strip(),
    }


# ---------------------------------------------------------------------------
# 2. Interview questions
# ---------------------------------------------------------------------------

def generate_interview_questions(
    resume_text: str,
    job_description: str,
    num_questions: int = 8
) -> list:
    """
    Generates interview questions based on the job and the resume.
    Returns a plain list of strings (same as before).
    """

    system_prompt = (
        "You are a hiring manager who is about to interview this candidate. "
        "Ask the questions you would really ask, not textbook ones.\n\n"
        + STYLE_RULES + "\n"
        "Rules for the questions:\n"
        "- Mix: about 40% technical, 30% resume-specific (mention a real project, "
        "tool or role from the resume), 30% behavioral.\n"
        "- Each question is one clear sentence, or two at most.\n"
        "- No generic questions like \"Tell me about yourself\".\n"
        "- Put the type at the start in brackets, like [Technical], [Resume], [Behavioral].\n\n"
        "Respond ONLY with valid JSON and no extra text. "
        'Use exactly this format: {"questions": [<strings>]}'
    )

    user_message = (
        f"JOB DESCRIPTION:\n{_trim(job_description)}\n\n"
        f"CANDIDATE RESUME:\n{_trim(resume_text)}\n\n"
        f"Write {num_questions} interview questions this candidate should prepare for."
    )

    data = _call_json(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        max_tokens=1500,
        temperature=TEMP_QUESTIONS,
    )

    questions = _as_str_list(_clean_structure(data.get("questions", [])))
    return questions[:num_questions]


# ---------------------------------------------------------------------------
# 3. Career coach chat
# ---------------------------------------------------------------------------

def chat_with_assistant(
    conversation_history: list,
    resume_text: str,
    job_description: str,
    user_message: str
) -> str:
    """
    Powers the free-form career coach chat.
    """

    system_prompt = (
        "You are an experienced career coach and ex-recruiter helping a candidate "
        "improve their resume and prepare for one specific job. "
        "Use the resume and job description below as context in every answer.\n\n"
        + STYLE_RULES + "\n"
        "Answer rules:\n"
        "- Keep it short: usually 3 to 6 sentences, or a short list if steps are needed.\n"
        "- When you suggest a rewrite, show it as Before / After.\n"
        "- If the question is unclear, ask one short follow-up question.\n"
        "- If the question has nothing to do with careers, jobs or this resume, "
        "politely bring the talk back to the candidate's job search.\n\n"
        f"JOB DESCRIPTION:\n{_trim(job_description)}\n\n"
        f"CANDIDATE RESUME:\n{_trim(resume_text)}"
    )

    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(conversation_history[-10:])  # keep last 10 turns only
    messages.append({"role": "user", "content": user_message})

    reply = _call_llm(messages, max_tokens=900, temperature=TEMP_CHAT)
    return _clean_text(reply)