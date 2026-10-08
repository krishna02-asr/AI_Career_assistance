"""
app.py

Streamlit front end for the Career Assistant.
Run locally with:  streamlit run app.py
"""

import os

import streamlit as st

import ai_engine
import ats
import database
import mock_interview
import utils

st.set_page_config(
    page_title="Career Assistant",
    page_icon="📄",
    layout="wide",
)

database.init_db()

# Small style tweaks: tighter spacing, cleaner cards, no default footer
st.markdown(
    """
    <style>
        #MainMenu, footer {visibility: hidden;}
        .block-container {padding-top: 2rem; max-width: 1200px;}
        div[data-testid="stMetric"] {
            background: rgba(128, 128, 128, 0.08);
            border: 1px solid rgba(128, 128, 128, 0.2);
            padding: 14px 18px;
            border-radius: 10px;
        }
        .tag {
            display: inline-block;
            padding: 2px 10px;
            margin-right: 6px;
            border-radius: 12px;
            font-size: 0.75rem;
            background: rgba(128, 128, 128, 0.18);
        }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------
defaults = {
    "current_result": None,
    "resume_text": "",
    "job_description": "",
    "job_title": "",
    "chat_history": [],
}
for key, value in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = value


def api_key_present() -> bool:
    if os.getenv("GROQ_API_KEY"):
        return True
    try:
        return bool(st.secrets["GROQ_API_KEY"])
    except Exception:
        return False


def score_label(score: int) -> str:
    if score >= 75:
        return "Strong"
    if score >= 50:
        return "Average"
    return "Needs work"


def split_tag(question: str):
    """'[Technical] How do you...' -> ('Technical', 'How do you...')"""
    if question.startswith("[") and "]" in question:
        tag, rest = question[1:].split("]", 1)
        return tag.strip(), rest.strip()
    return "", question


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
st.sidebar.title("Career Assistant")
st.sidebar.caption("Resume analysis and interview prep")

page = st.sidebar.radio(
    "Menu",
    ["New Analysis", "Mock Interview", "Career Chat", "History"],
    label_visibility="collapsed",
)

if not api_key_present():
    st.sidebar.error("GROQ_API_KEY is missing. Add it to .env or Streamlit secrets.")

# ===========================================================================
# New Analysis
# ===========================================================================
if page == "New Analysis":
    st.title("Resume Analysis")
    st.caption("Compare your resume with a job description and see what to fix first.")

    left, right = st.columns(2, gap="large")

    with left:
        st.subheader("Job description")
        job_title = st.text_input(
            "Job title",
            value=st.session_state.job_title,
            placeholder="Data Analyst",
        )
        job_description = st.text_area(
            "Job description",
            value=st.session_state.job_description,
            height=300,
            placeholder="Paste the full job posting here",
            label_visibility="collapsed",
        )

    with right:
        st.subheader("Your resume")
        upload = st.file_uploader("Upload a PDF", type=["pdf"])
        resume_text = st.text_area(
            "Resume text",
            value=st.session_state.resume_text,
            height=220,
            placeholder="Or paste your resume text here",
            label_visibility="collapsed",
        )

        if upload is not None:
            with st.spinner("Reading PDF"):
                resume_text = utils.extract_text_from_pdf(upload)
            st.caption(f"Read {len(resume_text):,} characters from the PDF.")

    if st.button("Analyze", type="primary", use_container_width=True):
        if not job_description.strip() or not resume_text.strip():
            st.error("Add both the job description and your resume first.")
        elif not api_key_present():
            st.error("API key not configured.")
        else:
            try:
                with st.spinner("Analyzing, this takes around 10 to 20 seconds"):
                    result = ai_engine.analyze_resume_vs_jd(resume_text, job_description)
                    result["interview_questions"] = ai_engine.generate_interview_questions(
                        resume_text, job_description
                    )
                    # Rule-based, no AI call: same input always gives the same score
                    result["ats"] = ats.compute_ats_score(resume_text, job_description)
            except Exception as err:
                st.error(f"Analysis failed. Please try again in a moment. ({err})")
            else:
                st.session_state.current_result = result
                st.session_state.resume_text = resume_text
                st.session_state.job_description = job_description
                st.session_state.job_title = job_title
                st.session_state.chat_history = []

                database.save_analysis(job_title, job_description, resume_text, result)
                st.toast("Analysis saved to history")

    # ----- results -----
    result = st.session_state.current_result
    if result:
        st.divider()

        match = int(result.get("match_percentage", 0))
        matching = result.get("matching_skills", [])
        missing = result.get("missing_skills", [])
        ats_data = result.get("ats")

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Job match", f"{match}%", score_label(match), delta_color="off")
        if ats_data:
            m2.metric("ATS score", f"{ats_data['ats_score']}%", ats_data["grade"], delta_color="off")
        else:
            m2.metric("ATS score", "NA")
        m3.metric("Skills matched", len(matching))
        m4.metric("Skills missing", len(missing))
        st.progress(min(match, 100) / 100)

        st.markdown("#### Verdict")
        st.write(result.get("summary", ""))

        tab_fixes, tab_ats, tab_skills, tab_sections, tab_questions = st.tabs(
            ["Top fixes", "ATS check", "Skills", "Section review", "Interview questions"]
        )

        # Top fixes with before / after
        with tab_fixes:
            fixes = result.get("top_fixes", [])
            if fixes:
                st.caption("Replace any [X] placeholders with your real numbers.")
                for i, fix in enumerate(fixes, 1):
                    with st.expander(f"{i}. {fix.get('issue', 'Fix')}", expanded=(i == 1)):
                        if fix.get("resume_line"):
                            st.caption("From your resume")
                            st.markdown(f"> {fix['resume_line']}")
                        st.write(fix.get("fix", ""))
                        b, a = st.columns(2)
                        with b:
                            st.caption("Before")
                            st.error(fix.get("before", ""))
                        with a:
                            st.caption("After")
                            st.success(fix.get("after", ""))
            else:
                # older saved results only have plain suggestions
                for i, tip in enumerate(result.get("suggestions", []), 1):
                    st.markdown(f"{i}. {tip}")

        # ATS compatibility
        with tab_ats:
            if ats_data:
                st.markdown(f"**ATS compatibility: {ats_data['ats_score']}/100 ({ats_data['grade']})**")
                st.progress(min(ats_data["ats_score"], 100) / 100)
                st.caption(ats_data["disclaimer"])

                st.markdown("#### Score breakdown")
                for item in ats_data["breakdown"]:
                    st.markdown(f"**{item['name']}**")
                    st.progress(
                        item["score"] / item["max"],
                        text=f"{item['score']:g} / {item['max']}",
                    )
                    st.caption(item["note"])

                if ats_data["tips"]:
                    st.markdown("#### Fix these first")
                    for i, tip in enumerate(ats_data["tips"], 1):
                        st.markdown(f"{i}. {tip}")

                k1, k2 = st.columns(2)
                with k1:
                    st.markdown("**Keywords found**")
                    st.write(", ".join(ats_data["matched_keywords"]) or "None")
                with k2:
                    st.markdown("**Keywords missing**")
                    st.write(", ".join(ats_data["missing_keywords"]) or "None")
            else:
                st.caption("ATS check is not available for this analysis.")

        # Skills
        with tab_skills:
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("**Already on your resume**")
                for skill in matching:
                    st.markdown(f"- {skill}")
                if not matching:
                    st.caption("Nothing matched.")
            with c2:
                st.markdown("**Missing for this job**")
                for skill in missing:
                    st.markdown(f"- {skill}")
                if not missing:
                    st.caption("No gaps found.")

            strengths = result.get("strengths", [])
            if strengths:
                st.markdown("**What's working**")
                for item in strengths:
                    st.markdown(f"- {item}")

        # Section review
        with tab_sections:
            sections = result.get("section_scores", {})
            if sections:
                for name, score in sections.items():
                    row_a, row_b = st.columns([1, 4])
                    row_a.write(f"**{name.capitalize()}**")
                    row_b.progress(min(int(score), 100) / 100, text=f"{score}/100  ·  {score_label(score)}")
            else:
                st.caption("Section scores are not available for this analysis.")

        # Interview questions
        with tab_questions:
            for i, q in enumerate(result.get("interview_questions", []), 1):
                tag, text = split_tag(q)
                label = f'<span class="tag">{tag}</span>' if tag else ""
                st.markdown(f"{i}. {label} {text}", unsafe_allow_html=True)

# ===========================================================================
# Mock Interview
# ===========================================================================
elif page == "Mock Interview":
    mock_interview.render()

# ===========================================================================
# History
# ===========================================================================
elif page == "History":
    st.title("History")

    analyses = database.get_all_analyses()

    if not analyses:
        st.info("Nothing here yet. Run an analysis first.")
    else:
        df = utils.analyses_to_dataframe(analyses)
        st.dataframe(df, use_container_width=True, hide_index=True)

        d1, d2 = st.columns(2)
        d1.download_button(
            "Download CSV",
            data=utils.export_to_csv_bytes(analyses),
            file_name="analyses.csv",
            mime="text/csv",
            use_container_width=True,
        )
        d2.download_button(
            "Download Excel",
            data=utils.export_to_excel_bytes(analyses),
            file_name="analyses.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )

        st.divider()
        with st.expander("Delete an entry"):
            entry_id = st.number_input("Entry ID", min_value=1, step=1)
            if st.button("Delete entry"):
                database.delete_analysis(int(entry_id))
                st.rerun()

# ===========================================================================
# Career Chat
# ===========================================================================
elif page == "Career Chat":
    st.title("Career Chat")

    if not st.session_state.job_description or not st.session_state.resume_text:
        st.info("Run an analysis first so the assistant knows your resume and the job.")
    else:
        st.caption(f"Context: {st.session_state.job_title or 'your job description'}")

        if not st.session_state.chat_history:
            st.markdown("**Try asking**")
            st.markdown(
                "- Rewrite my second project bullet to sound stronger\n"
                "- What would you cut from my resume for this role?\n"
                "- How should I answer a question about my skill gaps?"
            )

        for msg in st.session_state.chat_history:
            with st.chat_message(msg["role"]):
                st.write(msg["content"])

        user_input = st.chat_input("Ask about your resume or this job")
        if user_input:
            history = list(st.session_state.chat_history)
            st.session_state.chat_history.append({"role": "user", "content": user_input})
            with st.chat_message("user"):
                st.write(user_input)

            with st.chat_message("assistant"):
                try:
                    reply = ai_engine.chat_with_assistant(
                        history,
                        st.session_state.resume_text,
                        st.session_state.job_description,
                        user_input,
                    )
                except Exception:
                    reply = "I couldn't get a response just now. Please send that again."
                st.write(reply)

            st.session_state.chat_history.append({"role": "assistant", "content": reply})