import sqlite3
import json
from datetime import datetime

DB_NAME = "career_assistant.db"


def get_connection():
    """Create (or reuse) a connection to the local SQLite database file."""
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row  # lets us access columns by name
    return conn


def init_db():
    """
    Create the 'analyses' table if it doesn't already exist.
    Call this once when the app starts.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS analyses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            job_title TEXT,
            job_description TEXT NOT NULL,
            resume_text TEXT NOT NULL,
            match_percentage INTEGER,
            matching_skills TEXT,     -- stored as JSON text
            missing_skills TEXT,      -- stored as JSON text
            suggestions TEXT,         -- stored as JSON text
            interview_questions TEXT, -- stored as JSON text
            summary TEXT
        )
    """)
    conn.commit()
    conn.close()


def save_analysis(job_title, job_description, resume_text, result: dict):
    """
    Save one full analysis result into the database.
    `result` is the dictionary returned by ai_engine.analyze_resume_vs_jd()
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO analyses (
            created_at, job_title, job_description, resume_text,
            match_percentage, matching_skills, missing_skills,
            suggestions, interview_questions, summary
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        job_title,
        job_description,
        resume_text,
        result.get("match_percentage", 0),
        json.dumps(result.get("matching_skills", [])),
        json.dumps(result.get("missing_skills", [])),
        json.dumps(result.get("suggestions", [])),
        json.dumps(result.get("interview_questions", [])),
        result.get("summary", ""),
    ))
    conn.commit()
    new_id = cursor.lastrowid
    conn.close()
    return new_id


def get_all_analyses():
    """Return every saved analysis, most recent first."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM analyses ORDER BY id DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_analysis_by_id(analysis_id):
    """Return one specific analysis (used for the chat context)."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM analyses WHERE id = ?", (analysis_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def delete_analysis(analysis_id):
    """Delete one analysis by id."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM analyses WHERE id = ?", (analysis_id,))
    conn.commit()
    conn.close()