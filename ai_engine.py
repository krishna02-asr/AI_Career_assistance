"""
ai_engine.py
------------
This file is the "brain" of the project. Every function here talks to the
Groq API and turns a resume + job description into useful feedback.
"""

import os
import json
from groq import Groq
from dotenv import load_dotenv

load_dotenv()  # reads GROQ_API_KEY from .env

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

MODEL = "openai/gpt-oss-20b"


def _extract_json(text: str) -> dict:
    """
    Removes markdown JSON fences if the AI adds them
    and converts the response into a Python dictionary.
    """
    cleaned = text.strip()

    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")

        if cleaned.startswith("json"):
            cleaned = cleaned[4:].strip()

    return json.loads(cleaned)


def analyze_resume_vs_jd(resume_text: str, job_description: str) -> dict:
    """
    Compares the candidate's resume against the job description.

    Returns:
      - match_percentage
      - matching_skills
      - missing_skills
      - suggestions
      - summary
    """

    system_prompt = (
        "You are an expert technical recruiter and resume coach. "
        "You compare a candidate's resume against a job description. "
        "Respond ONLY with valid JSON, with no preamble and no markdown fences. "
        "Use exactly this schema:\n"
        "{\n"
        '  "match_percentage": <integer 0-100>,\n'
        '  "matching_skills": [<strings>],\n'
        '  "missing_skills": [<strings>],\n'
        '  "suggestions": [<strings>],\n'
        '  "summary": "<2-3 sentence overall verdict>"\n'
        "}"
    )

    user_message = (
        f"JOB DESCRIPTION:\n{job_description}\n\n"
        f"CANDIDATE RESUME:\n{resume_text}\n\n"
        "Analyze the fit and return the JSON exactly as specified."
    )

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        max_tokens=1500,
    )

    raw_text = response.choices[0].message.content

    return _extract_json(raw_text)


def generate_interview_questions(
    resume_text: str,
    job_description: str,
    num_questions: int = 8
) -> list:
    """
    Generates interview questions based on the job and resume.
    """

    system_prompt = (
        "You are a hiring manager preparing an interview. "
        "Respond ONLY with valid JSON and no extra text. "
        'Use exactly this format: {"questions": [<strings>]}'
    )

    user_message = (
        f"JOB DESCRIPTION:\n{job_description}\n\n"
        f"CANDIDATE RESUME:\n{resume_text}\n\n"
        f"Generate {num_questions} interview questions this candidate "
        "should prepare for. Include a mix of technical, behavioral, "
        "and resume-specific questions."
    )

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        max_tokens=1200,
    )

    raw_text = response.choices[0].message.content

    data = _extract_json(raw_text)

    return data.get("questions", [])


def chat_with_assistant(
    conversation_history: list,
    resume_text: str,
    job_description: str,
    user_message: str
) -> str:
    """
    Powers the free-form AI career coach chat.
    """

    system_prompt = (
        "You are a friendly, expert career coach helping a candidate "
        "improve their resume and interview preparation for a specific job. "
        "Use the resume and job description as context for every answer. "
        "Keep answers practical, specific, and concise.\n\n"
        f"JOB DESCRIPTION:\n{job_description}\n\n"
        f"CANDIDATE RESUME:\n{resume_text}"
    )

    messages = [
        {"role": "system", "content": system_prompt}
    ]

    messages.extend(conversation_history)

    messages.append(
        {"role": "user", "content": user_message}
    )

    response = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        max_tokens=800,
    )

    return response.choices[0].message.content