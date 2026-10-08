"""
ats.py

Rule-based ATS (Applicant Tracking System) compatibility check.
No AI call: the same resume + job description always gives the same score.

Used by app.py:  ats.compute_ats_score(resume_text, job_description)
"""

import re

DISCLAIMER = (
    "This is an estimate based on common ATS rules (keywords, sections, contact "
    "info, format). Real ATS software differs from company to company."
)

STOPWORDS = {
    "the", "and", "for", "with", "you", "your", "our", "are", "will", "from",
    "that", "this", "have", "has", "can", "not", "but", "all", "any", "who",
    "their", "they", "them", "its", "into", "out", "about", "also", "such",
    "etc", "per", "via", "able", "must", "should", "would", "could", "may",
    "more", "most", "other", "than", "then", "there", "these", "those", "what",
    "when", "where", "which", "while", "within", "without", "work", "working",
    "role", "job", "team", "teams", "company", "candidate", "candidates",
    "experience", "years", "year", "strong", "good", "excellent", "knowledge",
    "ability", "skills", "skill", "required", "preferred", "responsibilities",
    "responsibility", "requirements", "qualification", "qualifications",
    "including", "using", "use", "used", "ensure", "help", "make", "new",
    "join", "looking", "seeking", "hiring", "position", "opportunity",
    "across", "based", "well", "both", "each", "one", "two", "like", "etc.",
    "being", "been", "was", "were", "how", "why", "yet", "get", "got", "day",
    "plus", "part", "full", "time", "love", "great", "high", "key", "various",
}

SECTION_PATTERNS = {
    "Experience": r"\b(work experience|professional experience|experience|employment|internship[s]?)\b",
    "Education": r"\b(education|academic|qualification[s]?)\b",
    "Skills": r"\b(skills|technical skills|core competencies|technologies)\b",
    "Projects / Summary": r"\b(projects?|summary|objective|profile|achievements?)\b",
}


def _tokens(text: str):
    return re.findall(r"[a-zA-Z][a-zA-Z0-9+#.\-]{1,}", text.lower())


def _clean(token: str) -> str:
    return token.strip(".-")


def _extract_keywords(job_description: str, limit: int = 25):
    """Most frequent meaningful words in the JD (ties broken by first appearance)."""
    counts = {}
    order = {}
    for i, raw in enumerate(_tokens(job_description)):
        word = _clean(raw)
        if len(word) < 3 or word in STOPWORDS or word.isdigit():
            continue
        counts[word] = counts.get(word, 0) + 1
        order.setdefault(word, i)
    ranked = sorted(counts, key=lambda w: (-counts[w], order[w]))
    return ranked[:limit]


def _grade(score: float) -> str:
    if score >= 75:
        return "Strong"
    if score >= 50:
        return "Average"
    return "Needs work"


def compute_ats_score(resume_text: str, job_description: str) -> dict:
    resume = resume_text or ""
    resume_lower = resume.lower()
    resume_words = {_clean(t) for t in _tokens(resume)}

    breakdown = []
    tips = []

    # ---- 1. Keyword match (50) ------------------------------------------
    keywords = _extract_keywords(job_description or "")
    matched = [k for k in keywords if k in resume_words]
    missing = [k for k in keywords if k not in resume_words]
    kw_max = 50
    kw_score = round(kw_max * len(matched) / len(keywords), 1) if keywords else 0
    breakdown.append({
        "name": "Keyword match",
        "score": kw_score,
        "max": kw_max,
        "note": f"{len(matched)} of {len(keywords)} important job keywords found in your resume.",
    })
    if missing:
        tips.append(
            "Add the missing keywords where they are true for you: "
            + ", ".join(missing[:8]) + "."
        )

    # ---- 2. Standard sections (20) --------------------------------------
    found_sections = [
        name for name, pattern in SECTION_PATTERNS.items()
        if re.search(pattern, resume_lower)
    ]
    sec_max = 20
    sec_score = round(sec_max * len(found_sections) / len(SECTION_PATTERNS), 1)
    breakdown.append({
        "name": "Standard sections",
        "score": sec_score,
        "max": sec_max,
        "note": "Found: " + (", ".join(found_sections) or "none") + ".",
    })
    for name in SECTION_PATTERNS:
        if name not in found_sections:
            tips.append(f"Add a clearly labelled '{name.split(' /')[0]}' section heading.")

    # ---- 3. Contact info (15) -------------------------------------------
    has_email = bool(re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", resume))
    has_phone = bool(re.search(r"(\+?\d[\d\s\-()]{8,}\d)", resume))
    has_link = bool(re.search(r"(linkedin\.com|github\.com)", resume_lower))
    con_score = 5 * has_email + 5 * has_phone + 5 * has_link
    present = [n for n, ok in (("email", has_email), ("phone", has_phone), ("LinkedIn/GitHub", has_link)) if ok]
    breakdown.append({
        "name": "Contact info",
        "score": con_score,
        "max": 15,
        "note": "Found: " + (", ".join(present) or "none") + ".",
    })
    if not has_email:
        tips.append("Add a professional email address at the top.")
    if not has_phone:
        tips.append("Add a phone number at the top.")
    if not has_link:
        tips.append("Add your LinkedIn or GitHub link.")

    # ---- 4. Length and format (15) --------------------------------------
    word_count = len(resume.split())
    if 300 <= word_count <= 900:
        len_score = 8
        len_note = f"{word_count} words, a good length."
    elif 150 <= word_count < 300 or 900 < word_count <= 1200:
        len_score = 4
        len_note = f"{word_count} words, a bit off the ideal 300 to 900."
        tips.append("Aim for roughly 300 to 900 words (1 to 2 pages).")
    else:
        len_score = 1
        len_note = f"{word_count} words, far from the ideal 300 to 900."
        tips.append("Aim for roughly 300 to 900 words (1 to 2 pages).")

    has_bullets = bool(re.search(r"(^|\n)\s*[-•*▪●]\s+\S", resume))
    has_numbers = len(re.findall(r"\d+\s?%|\$\s?\d|\b\d{2,}\b", resume)) >= 3
    fmt_score = len_score + (3 if has_bullets else 0) + (4 if has_numbers else 0)
    notes = [len_note]
    notes.append("Bullet points used." if has_bullets else "No bullet points detected.")
    notes.append("Numbers/metrics used." if has_numbers else "Few numbers or metrics.")
    breakdown.append({
        "name": "Length and format",
        "score": fmt_score,
        "max": 15,
        "note": " ".join(notes),
    })
    if not has_bullets:
        tips.append("Use bullet points for experience and projects.")
    if not has_numbers:
        tips.append("Add numbers to your bullets (%, counts, amounts) to show impact.")

    total = round(sum(item["score"] for item in breakdown))
    total = max(0, min(100, total))

    return {
        "ats_score": total,
        "grade": _grade(total),
        "disclaimer": DISCLAIMER,
        "breakdown": breakdown,
        "tips": tips[:6],
        "matched_keywords": matched,
        "missing_keywords": missing,
    }