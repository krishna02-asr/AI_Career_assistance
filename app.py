"""
app.py
------
Entry point for the AI Career Assistant.
Run with:  streamlit run app.py

This file only handles the UI / user interaction. All the "smart" work is
delegated to ai_engine.py (Claude API calls), database.py (SQLite storage)
and utils.py (PDF reading + Excel/CSV export).
"""

import streamlit as st
import database
import ai_engine
import utils

st.set_page_config(page_title="AI Career Assistant", page_icon="🧑‍💼", layout="wide")

# Make sure the database + table exist before anything else runs.
database.init_db()

# ---------------------------------------------------------------------------
# Session state: values that need to survive between reruns of the script
# (Streamlit reruns the whole file on every interaction).
# ---------------------------------------------------------------------------
if "current_result" not in st.session_state:
    st.session_state.current_result = None
if "resume_text" not in st.session_state:
    st.session_state.resume_text = ""
if "job_description" not in st.session_state:
    st.session_state.job_description = ""
if "job_title" not in st.session_state:
    st.session_state.job_title = ""
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []  # list of {"role": ..., "content": ...}

# ---------------------------------------------------------------------------
# Sidebar navigation
# ---------------------------------------------------------------------------
st.sidebar.title("🧑‍💼 AI Career Assistant")
page = st.sidebar.radio("Go to", ["🔍 New Analysis", "📊 History & Export", "💬 Chat with AI"])

if not __import__("os").getenv("GROQ_API_KEY"):
    st.sidebar.warning("⚠️ GROQ_API_KEY not set. Add it to your .env file.")

# ===========================================================================
# PAGE 1: New Analysis
# ===========================================================================
if page == "🔍 New Analysis":
    st.title("Resume vs Job Description Analyzer")
    st.caption("Paste a job description, add your resume, and let AI do the rest.")

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("1. Job Description")
        job_title = st.text_input("Job title", value=st.session_state.job_title, placeholder="e.g. Data Analyst")
        job_description = st.text_area(
            "Paste the full job description here",
            value=st.session_state.job_description,
            height=300,
            placeholder="Paste the JD text...",
        )

    with col2:
        st.subheader("2. Your Resume")
        upload = st.file_uploader("Upload resume (PDF)", type=["pdf"])
        resume_text = st.text_area(
            "...or paste your resume text here",
            value=st.session_state.resume_text,
            height=260,
            placeholder="Paste resume text, or upload a PDF above",
        )

        if upload is not None:
            with st.spinner("Reading PDF..."):
                resume_text = utils.extract_text_from_pdf(upload)
            st.success(f"Extracted {len(resume_text)} characters from PDF.")

    st.divider()

    if st.button("🚀 Analyze Resume", type="primary", use_container_width=True):
        if not job_description.strip() or not resume_text.strip():
            st.error("Please provide both a job description and a resume.")
        else:
            with st.spinner("AI is analyzing your resume against the job description..."):
                result = ai_engine.analyze_resume_vs_jd(resume_text, job_description)
                questions = ai_engine.generate_interview_questions(resume_text, job_description)
                result["interview_questions"] = questions

            # Save everything to session state so it survives page switches
            st.session_state.current_result = result
            st.session_state.resume_text = resume_text
            st.session_state.job_description = job_description
            st.session_state.job_title = job_title
            st.session_state.chat_history = []  # reset chat for the new analysis

            # Persist to SQLite immediately
            database.save_analysis(job_title, job_description, resume_text, result)
            st.success("Analysis complete and saved!")

    # -----------------------------------------------------------------------
    # Show results (if we have any for this session)
    # -----------------------------------------------------------------------
    result = st.session_state.current_result
    if result:
        st.divider()
        st.header("Results")

        m1, m2, m3 = st.columns(3)
        m1.metric("Match Percentage", f"{result.get('match_percentage', 0)}%")
        m2.metric("Matching Skills", len(result.get("matching_skills", [])))
        m3.metric("Missing Skills", len(result.get("missing_skills", [])))

        st.progress(min(int(result.get("match_percentage", 0)), 100) / 100)

        st.subheader("📝 Summary")
        st.write(result.get("summary", ""))

        c1, c2 = st.columns(2)
        with c1:
            st.subheader("✅ Matching Skills")
            for skill in result.get("matching_skills", []):
                st.markdown(f"- {skill}")
        with c2:
            st.subheader("❌ Missing Skills")
            for skill in result.get("missing_skills", []):
                st.markdown(f"- {skill}")

        st.subheader("💡 Suggestions to Improve Your Resume")
        for i, suggestion in enumerate(result.get("suggestions", []), 1):
            st.markdown(f"{i}. {suggestion}")

        st.subheader("🎤 Likely Interview Questions")
        for i, q in enumerate(result.get("interview_questions", []), 1):
            st.markdown(f"{i}. {q}")

# ===========================================================================
# PAGE 2: History & Export
# ===========================================================================
elif page == "📊 History & Export":
    st.title("Past Analyses")

    analyses = database.get_all_analyses()

    if not analyses:
        st.info("No analyses saved yet. Run one from the 'New Analysis' page.")
    else:
        df = utils.analyses_to_dataframe(analyses)
        st.dataframe(df, use_container_width=True, hide_index=True)

        col1, col2 = st.columns(2)
        with col1:
            st.download_button(
                "⬇️ Download as CSV",
                data=utils.export_to_csv_bytes(analyses),
                file_name="career_assistant_analyses.csv",
                mime="text/csv",
                use_container_width=True,
            )
        with col2:
            st.download_button(
                "⬇️ Download as Excel",
                data=utils.export_to_excel_bytes(analyses),
                file_name="career_assistant_analyses.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )

        st.divider()
        st.subheader("Delete an entry")
        id_to_delete = st.number_input("Analysis ID", min_value=1, step=1)
        if st.button("🗑️ Delete"):
            database.delete_analysis(int(id_to_delete))
            st.success(f"Deleted analysis #{id_to_delete}. Refresh the page to update the table.")

# ===========================================================================
# PAGE 3: Chat with AI
# ===========================================================================
elif page == "💬 Chat with AI":
    st.title("Chat with your Career Assistant")

    if not st.session_state.job_description or not st.session_state.resume_text:
        st.info("Run an analysis first (on the 'New Analysis' page) so the AI has context to chat about.")
    else:
        st.caption(f"Chatting in context of: **{st.session_state.job_title or 'your job description'}**")

        # Replay chat history
        for msg in st.session_state.chat_history:
            with st.chat_message(msg["role"]):
                st.write(msg["content"])

        user_input = st.chat_input("Ask about your resume, this job, or interview prep...")
        if user_input:
            st.session_state.chat_history.append({"role": "user", "content": user_input})
            with st.chat_message("user"):
                st.write(user_input)

            with st.chat_message("assistant"):
                with st.spinner("Thinking..."):
                    reply = ai_engine.chat_with_assistant(
                        st.session_state.chat_history[:-1],  # history before this message
                        st.session_state.resume_text,
                        st.session_state.job_description,
                        user_input,
                    )
                st.write(reply)

            st.session_state.chat_history.append({"role": "assistant", "content": reply})