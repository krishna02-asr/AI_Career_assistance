🧑‍💼 AI Career Assistant
A GenAI-powered app that compares a resume against a job description and gives: match %, matching/missing skills, resume improvement suggestions, tailored interview questions, a chat assistant for follow-up questions, SQLite storage of every past analysis, and CSV/Excel export.
PART 1 — How to run it (step by step)
Step 1: Install Python
You need Python 3.9 or newer. Check with:
python3 --version
If you don't have it, download from https://python.org.
Step 2: Get the project files
Unzip/place all 6 files (app.py, database.py, ai_engine.py, utils.py, requirements.txt, .env.example) into one folder, e.g. career_ai_assistant/.
Step 3: Create a virtual environment (recommended, not required)
cd career_ai_assistant
python3 -m venv venv
source venv/bin/activate       # Mac/Linux
venv\Scripts\activate          # Windows
Step 4: Install dependencies
pip install -r requirements.txt
Step 5: Get an Anthropic (Claude) API key
Go to https://console.anthropic.com and sign up.
Go to "API Keys" → "Create Key".
Copy the key (starts with sk-ant-...).
Step 6: Add your API key
Rename .env.example to .env and paste your key in:
ANTHROPIC_API_KEY=sk-ant-your-real-key-here
This file is read automatically by ai_engine.py — never share this file or commit it to GitHub (add .env to your .gitignore).
Step 7: Run the app
streamlit run app.py
Your browser will open automatically at http://localhost:8501.
Step 8: Use it
Go to New Analysis → paste a job description, upload/paste your resume.
Click Analyze Resume → see match %, missing skills, suggestions, interview questions.
Go to History & Export → see every past analysis, download as CSV or Excel.
Go to Chat with AI → ask follow-up questions like "how do I phrase my Python project better for this job?"
A file called career_assistant.db will automatically be created in the folder — that's your SQLite database. You don't need to install any separate database software.
PART 2 — How the project works (plain-English explanation)
Think of the app as 4 puzzle pieces, each in its own file:
1. app.py — The face of the app (what the user sees)
Built with Streamlit, a Python library that turns a plain script into a web app with almost no HTML/CSS/JS needed. It has 3 pages (New Analysis, History, Chat), and it "remembers" things like the current resume and chat history using st.session_state — Streamlit's way of keeping data between clicks (because Streamlit re-runs the whole script every time you interact with it).
2. ai_engine.py — The brain (talks to Claude)
This is the actual "GenAI" part. It sends your resume + job description to Anthropic's Claude API and asks it to respond as structured JSON (e.g. {"match_percentage": 78, "missing_skills": [...]}) instead of free text. That's the key trick that makes an LLM usable inside a real app: instead of getting a paragraph you'd have to read yourself, you get data your Python code can directly use to build metrics, tables, and charts.
There are 3 functions:
analyze_resume_vs_jd() → match %, skills, suggestions, summary
generate_interview_questions() → a tailored question list
chat_with_assistant() → free-form conversation, using the resume + JD as background context so answers stay relevant
3. database.py — The memory (SQLite)
Every time you run an analysis, it's saved as one row in a local SQLite database file. SQLite is a full SQL database that lives in a single file — no server setup needed, which makes it perfect for a portfolio project. The functions here are just standard INSERT/SELECT/DELETE SQL statements wrapped in Python functions.
4. utils.py — The utility belt
Two jobs:
Reads text out of an uploaded PDF resume (using pypdf), so users don't have to manually copy-paste their resume.
Converts the saved database rows into a CSV or Excel file (using pandas + openpyxl) that the user can download with one click.
The overall flow
User pastes JD + uploads resume
        ↓
app.py collects the input
        ↓
ai_engine.py sends it to Claude API → gets back structured JSON
        ↓
app.py displays match %, skills, suggestions, questions
        ↓
database.py saves the full result to SQLite
        ↓
utils.py can export all saved results to CSV/Excel anytime
        ↓
User can also open the Chat tab to ask Claude follow-up questions
PART 3 — Why this is a strong resume project
You can honestly describe this project as:
Built a full-stack GenAI application that uses the Claude API to analyze resumes against job descriptions, generating match scores, skill gap analysis, and tailored interview questions; implemented SQLite for persistent storage and Streamlit for the UI, with CSV/Excel export.
It touches skills recruiters look for:
LLM / GenAI integration (prompt engineering, structured JSON output)
Full-stack thinking (UI → logic → database, cleanly separated into files)
SQL / database design
File handling (PDF parsing)
Data export (pandas, Excel/CSV generation)
Python software engineering practices (modular files, not one giant script)
PART 4 — Common issues
Problem
Fix
ANTHROPIC_API_KEY not set warning
Make sure .env exists (not .env.example) and has your real key
PDF upload extracts empty text
The PDF is likely a scanned image, not real text — paste the resume text manually instead
JSONDecodeError in terminal
Rare — Claude occasionally adds extra text; rerun the analysis. You can also lower max_tokens risk by keeping resumes under ~2 pages
Streamlit says "command not found"
Activate your virtual environment first, or use python3 -m streamlit run app.py
Possible future upgrades (mention these in interviews as "next steps")
Support DOCX resumes, not just PDF
Let users compare one resume against multiple job descriptions at once
Add authentication so multiple users can have separate histories
Switch SQLite → PostgreSQL for a production deployment
Deploy on Streamlit Community Cloud for a live demo link on your resume