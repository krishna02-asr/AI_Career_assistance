"""
mock_interview.py

Video-call style mock interview.

- Your camera turns on (live preview, nothing is recorded or uploaded)
- An AI recruiter shows each question on screen AND speaks it
- You answer with your microphone (transcribed with Groq Whisper) or by typing
- After 5 to 10 questions you get a score and feedback for every answer

app.py calls:  mock_interview.render()
"""

import html
import json
import os
from io import BytesIO

import streamlit as st
import streamlit.components.v1 as components

try:
    from gtts import gTTS  # optional: server-side voice for the recruiter
except Exception:
    gTTS = None

try:
    import utils  # only used for PDF resume upload
except Exception:
    utils = None

try:
    import ai_engine  # reuse the model name that already works in your project
except Exception:
    ai_engine = None


def _available_models() -> list:
    cached = st.session_state.get("mi_models")
    if cached:
        return cached
    from groq import Groq

    ids = [m.id for m in Groq(api_key=_get_api_key()).models.list().data]
    st.session_state["mi_models"] = ids
    return ids


def _chat_model() -> str:
    # 1) Use the same model your ai_engine.py already uses, if it exposes one
    if ai_engine is not None:
        for name in ("MODEL", "MODEL_NAME", "GROQ_MODEL", "CHAT_MODEL", "LLM_MODEL"):
            value = getattr(ai_engine, name, None)
            if isinstance(value, str) and value:
                return value

    # 2) Otherwise pick a chat model that your Groq account actually has
    skip = ("whisper", "tts", "guard", "playai", "orpheus", "safeguard", "embed")
    chat = [m for m in _available_models() if not any(s in m.lower() for s in skip)]
    for preferred in ("llama-3.3-70b", "gpt-oss-120b", "llama-4", "qwen", "gpt-oss-20b", "llama-3.1"):
        for model in chat:
            if preferred in model.lower():
                return model
    if chat:
        return chat[0]
    raise ValueError("No chat model is available on your Groq account.")


def _whisper_model() -> str:
    names = [m for m in _available_models() if "whisper" in m.lower()]
    for model in names:
        if "turbo" in model.lower():
            return model
    return names[0] if names else "whisper-large-v3"


# ---------------------------------------------------------------------------
# Groq helpers
# ---------------------------------------------------------------------------
def _get_api_key() -> str:
    key = os.getenv("GROQ_API_KEY")
    if key:
        return key
    try:
        return st.secrets["GROQ_API_KEY"]
    except Exception:
        return ""


def _client():
    from groq import Groq

    return Groq(api_key=_get_api_key())


def _json_chat(system: str, user: str, temperature: float = 0.4) -> dict:
    resp = _client().chat.completions.create(
        model=_chat_model(),
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=temperature,
        response_format={"type": "json_object"},
    )
    return json.loads(resp.choices[0].message.content)


def generate_questions(resume: str, jd: str, role: str, n: int) -> list:
    system = (
        "You are a friendly but sharp recruiter running a live interview. "
        "Reply with JSON only."
    )
    user = f"""Create exactly {n} interview questions for this candidate.

Role: {role or "Not specified"}

Resume:
{resume[:6000]}

Job description (may be empty):
{jd[:3000] or "Not provided"}

Rules:
- Question 1 must be a short warm-up like "Tell me about yourself".
- Most questions must be based on the candidate's actual projects, skills and experience from the resume.
- Include 1 or 2 questions on skills the job needs but the resume lacks (if a job description is given).
- Include 1 behavioural question and the last one situational.
- Each question must be one or two sentences, easy to understand when spoken aloud.

Return JSON: {{"questions": [{{"type": "Warm-up|Resume|Technical|Behavioural|Situational", "question": "..."}}]}}"""
    data = _json_chat(system, user, temperature=0.6)

    questions = []
    for item in data.get("questions", []):
        if isinstance(item, dict):
            text = str(item.get("question", "")).strip()
            kind = str(item.get("type", "")).strip()
        else:
            text, kind = str(item).strip(), ""
        if text:
            questions.append({"type": kind, "question": text})
    if not questions:
        raise ValueError("The AI did not return any questions.")
    return questions[:n]


def transcribe(audio_bytes: bytes) -> str:
    result = _client().audio.transcriptions.create(
        file=("answer.wav", audio_bytes),
        model=_whisper_model(),
        language="en",
        response_format="text",
    )
    text = result if isinstance(result, str) else getattr(result, "text", "")
    return text.strip()


def evaluate(resume: str, jd: str, role: str, qa: list) -> dict:
    system = (
        "You are a strict but supportive interview coach. Judge only what the "
        "candidate actually said. Reply with JSON only."
    )
    blocks = []
    for i, item in enumerate(qa, 1):
        answer = item["answer"].strip() or "(skipped, no answer given)"
        blocks.append(f"Q{i}: {item['question']}\nAnswer {i}: {answer}")
    joined = "\n\n".join(blocks)

    user = f"""Evaluate this mock interview.

Role: {role or "Not specified"}

Resume:
{resume[:4000]}

Job description (may be empty):
{jd[:2000] or "Not provided"}

Interview:
{joined}

Rules:
- Score each answer 0 to 10 (skipped = 0). Judge relevance, clarity, specifics and structure.
- feedback: 2 to 3 sentences, specific to that answer.
- better_answer: a short stronger version of the answer (3 to 5 sentences). Do not invent experience the resume does not show; use [X] as a placeholder for numbers.
- overall_score: 0 to 100.
- strengths and improvements: 3 short points each.

Return JSON:
{{"overall_score": 0, "verdict": "2 sentences",
"strengths": ["..."], "improvements": ["..."],
"questions": [{{"score": 0, "feedback": "...", "better_answer": "..."}}]}}
The "questions" array must have exactly {len(qa)} items in the same order."""
    return _json_chat(system, user, temperature=0.3)


# ---------------------------------------------------------------------------
# Voice + video widgets
# ---------------------------------------------------------------------------
CAMERA_HTML = """
<div style="position:relative;font-family:sans-serif;">
  <video id="v" autoplay playsinline muted
         style="width:100%;height:330px;object-fit:cover;border-radius:14px;
                background:#111;transform:scaleX(-1);"></video>
  <div id="msg" style="position:absolute;left:12px;right:12px;top:50%;
       transform:translateY(-50%);color:#fff;text-align:center;font-size:14px;"></div>
  <div style="position:absolute;left:12px;bottom:12px;background:rgba(0,0,0,.55);
       color:#fff;padding:3px 10px;border-radius:8px;font-size:13px;">You</div>
  <div style="position:absolute;right:12px;top:12px;background:rgba(0,0,0,.55);
       color:#fff;padding:3px 10px;border-radius:8px;font-size:12px;">
       <span style="color:#ff4d4d;">&#9679;</span> LIVE</div>
</div>
<script>
  const v = document.getElementById('v');
  const msg = document.getElementById('msg');
  msg.textContent = 'Allow camera access in your browser...';
  navigator.mediaDevices.getUserMedia({video: true, audio: false})
    .then(function (stream) { v.srcObject = stream; msg.textContent = ''; })
    .catch(function () {
      msg.textContent = 'Camera is blocked. Click the lock icon in the address bar, allow Camera, then refresh the page.';
    });
</script>
"""


def _recruiter_html(question: dict, browser_voice: bool, autoplay: bool) -> str:
    """Recruiter tile. If browser_voice is True it also speaks the question itself."""
    text = html.escape(question["question"])
    kind = html.escape(question.get("type", ""))
    tag = (
        f'<span style="background:rgba(255,255,255,.18);padding:2px 10px;'
        f'border-radius:12px;font-size:12px;">{kind}</span>'
        if kind
        else ""
    )

    speech = ""
    if browser_voice:
        js_text = json.dumps(question["question"]).replace("</", "<\\/")
        speech = f"""
        <button id="rep" style="margin-top:14px;padding:6px 14px;border-radius:8px;
                border:none;cursor:pointer;">&#128266; Repeat question</button>
        <script>
          const qText = {js_text};
          function speak() {{
            window.speechSynthesis.cancel();
            const u = new SpeechSynthesisUtterance(qText);
            u.lang = 'en-US'; u.rate = 0.95;
            window.speechSynthesis.speak(u);
          }}
          document.getElementById('rep').onclick = speak;
          if ({str(autoplay).lower()}) {{ setTimeout(speak, 400); }}
        </script>
        """

    return f"""
    <div style="font-family:sans-serif;height:330px;box-sizing:border-box;
         border-radius:14px;padding:22px;color:#fff;overflow:auto;
         background:linear-gradient(145deg,#1f2a44,#2d3a63);">
      <div style="display:flex;align-items:center;gap:12px;margin-bottom:16px;">
        <div style="width:46px;height:46px;border-radius:50%;background:#4f7cff;
             display:flex;align-items:center;justify-content:center;font-size:24px;">
             &#129489;&#8205;&#128188;</div>
        <div><div style="font-weight:600;">AI Recruiter</div>
             <div style="font-size:12px;opacity:.8;">Interviewer</div></div>
        <div style="margin-left:auto;">{tag}</div>
      </div>
      <div style="font-size:19px;line-height:1.5;">{text}</div>
      {speech}
    </div>
    """


def _tts_bytes(index: int, text: str):
    cache = st.session_state.setdefault("mi_tts", {})
    if index not in cache:
        buf = BytesIO()
        gTTS(text=text, lang="en").write_to_fp(buf)
        cache[index] = buf.getvalue()
    return cache[index]


# ---------------------------------------------------------------------------
# Session helpers
# ---------------------------------------------------------------------------
def _reset():
    for key in list(st.session_state.keys()):
        if key.startswith("mi_"):
            del st.session_state[key]


def _label(score10: float) -> str:
    if score10 >= 7.5:
        return "Strong"
    if score10 >= 5:
        return "Average"
    return "Needs work"


def _finish(qa_done: list):
    resume = st.session_state.get("mi_resume", "")
    jd = st.session_state.get("mi_jd", "")
    role = st.session_state.get("mi_role", "")
    try:
        with st.spinner("Evaluating your answers, this takes around 15 seconds"):
            report = evaluate(resume, jd, role, qa_done)
    except Exception as err:
        st.error(f"Could not evaluate the interview. Please try again. ({err})")
        return
    st.session_state.mi_report = report
    st.session_state.mi_qa_done = qa_done
    st.session_state.mi_stage = "result"
    st.rerun()


# ---------------------------------------------------------------------------
# Stages
# ---------------------------------------------------------------------------
def _setup_stage():
    st.caption(
        "The AI recruiter interviews you based on your resume. Your camera turns on, "
        "each question appears on screen and is spoken aloud, and you answer with your voice."
    )

    resume_default = st.session_state.get("resume_text", "")
    upload = st.file_uploader("Upload resume (PDF)", type=["pdf"], key="mi_upload")
    resume_text = st.text_area(
        "Resume text",
        value=resume_default,
        height=200,
        placeholder="Paste your resume here, or upload a PDF above",
    )
    if upload is not None and utils is not None:
        try:
            resume_text = utils.extract_text_from_pdf(upload)
            st.caption(f"Read {len(resume_text):,} characters from the PDF.")
        except Exception:
            st.warning("Could not read that PDF. Paste the text instead.")

    c1, c2 = st.columns(2)
    role = c1.text_input("Job title (optional)", value=st.session_state.get("job_title", ""))
    n = c2.slider("Number of questions", 5, 10, 6)
    jd = st.text_area(
        "Job description (optional)",
        value=st.session_state.get("job_description", ""),
        height=120,
        placeholder="Paste the job description to get questions tailored to the job",
    )

    st.info(
        "When you start, your browser will ask for Camera and Microphone permission. "
        "Click Allow. Use Chrome or Edge for best results."
    )

    if st.button("Start interview", type="primary", use_container_width=True):
        if not _get_api_key():
            st.error("GROQ_API_KEY is missing. Add it to .env or Streamlit secrets.")
            return
        if not resume_text.strip():
            st.error("Add your resume first.")
            return
        try:
            with st.spinner("Preparing your interview"):
                questions = generate_questions(resume_text, jd, role, n)
        except Exception as err:
            st.error(f"Could not create questions. Please try again. ({err})")
            return

        _reset()
        st.session_state.mi_resume = resume_text
        st.session_state.mi_jd = jd
        st.session_state.mi_role = role
        st.session_state.mi_questions = questions
        st.session_state.mi_answers = []
        st.session_state.mi_idx = 0
        st.session_state.mi_stage = "interview"
        st.rerun()


def _interview_stage():
    questions = st.session_state.mi_questions
    total = len(questions)
    i = st.session_state.mi_idx
    question = questions[i]

    st.progress(i / total, text=f"Question {i + 1} of {total}")

    # Speak each question only once, not on every rerun
    first_time = st.session_state.get("mi_spoken") != i
    use_server_voice = gTTS is not None

    col_cam, col_ai = st.columns(2, gap="medium")
    with col_cam:
        components.html(CAMERA_HTML, height=340)
    with col_ai:
        components.html(
            _recruiter_html(question, browser_voice=not use_server_voice, autoplay=first_time),
            height=340,
        )

    if use_server_voice:
        try:
            st.audio(_tts_bytes(i, question["question"]), format="audio/mp3", autoplay=first_time)
        except Exception:
            st.caption("Voice is not available right now. Read the question on screen.")
    st.session_state.mi_spoken = i
    st.caption("Can't hear the question? Press play above, or read it on screen.")

    st.markdown("#### Your answer")
    text_key = f"mi_text_{i}"

    if hasattr(st, "audio_input"):
        audio = st.audio_input("Click the mic, speak your answer, then stop", key=f"mi_audio_{i}")
        if audio is not None:
            data = audio.getvalue()
            signature = f"{len(data)}-{hash(data)}"
            if st.session_state.get(f"mi_sig_{i}") != signature:
                try:
                    with st.spinner("Converting your voice to text"):
                        st.session_state[text_key] = transcribe(data)
                    st.session_state[f"mi_sig_{i}"] = signature
                except Exception as err:
                    st.exception(err)
    else:
        st.warning("Voice answers need a newer Streamlit (pip install -U streamlit). Type your answer for now.")

    answer = st.text_area(
        "Your answer (edit it if the voice-to-text made a mistake)",
        key=text_key,
        height=140,
    )

    b1, b2, b3 = st.columns(3)
    submit = b1.button("Submit and next", type="primary", use_container_width=True)
    skip = b2.button("Skip question", use_container_width=True)
    end = b3.button("End and get result", use_container_width=True)

    if submit and not answer.strip():
        st.warning("Record or type an answer first, or press Skip.")
        return

    if submit or skip or end:
        recorded = answer.strip() if submit else ""
        st.session_state.mi_answers.append(recorded)

        if end or i + 1 >= total:
            done = [
                {"question": questions[k]["question"], "answer": a}
                for k, a in enumerate(st.session_state.mi_answers)
            ]
            _finish(done)
        else:
            st.session_state.mi_idx = i + 1
            st.rerun()


def _result_stage():
    report = st.session_state.get("mi_report", {})
    qa_done = st.session_state.get("mi_qa_done", [])
    per_q = report.get("questions", [])

    overall = int(report.get("overall_score", 0) or 0)
    answered = sum(1 for item in qa_done if item["answer"].strip())

    m1, m2, m3 = st.columns(3)
    m1.metric("Overall score", f"{overall}/100")
    m2.metric("Questions answered", f"{answered}/{len(qa_done)}")
    avg = (
        sum(float(q.get("score", 0) or 0) for q in per_q) / len(per_q) if per_q else 0
    )
    m3.metric("Average per answer", f"{avg:.1f}/10")
    st.progress(min(max(overall, 0), 100) / 100)

    st.markdown("#### Verdict")
    st.write(report.get("verdict", ""))

    s_col, i_col = st.columns(2)
    with s_col:
        st.markdown("**What went well**")
        for item in report.get("strengths", []):
            st.markdown(f"- {item}")
    with i_col:
        st.markdown("**Work on these**")
        for item in report.get("improvements", []):
            st.markdown(f"- {item}")

    st.markdown("#### Answer by answer")
    for k, item in enumerate(qa_done):
        entry = per_q[k] if k < len(per_q) else {}
        score = float(entry.get("score", 0) or 0)
        with st.expander(f"Q{k + 1}. {item['question']}  ·  {score:g}/10 ({_label(score)})", expanded=(k == 0)):
            st.caption("Your answer")
            st.write(item["answer"] or "Skipped")
            st.caption("Feedback")
            st.write(entry.get("feedback", ""))
            if entry.get("better_answer"):
                st.caption("A stronger answer")
                st.success(entry["better_answer"])

    st.caption(
        "Your camera is only a live preview to make practice feel real. Video is not "
        "recorded or analysed. Scores are based on what you said."
    )

    if st.button("Start a new interview", type="primary", use_container_width=True):
        _reset()
        st.rerun()


# ---------------------------------------------------------------------------
# Entry point used by app.py
# ---------------------------------------------------------------------------
def render():
    st.title("Mock Interview")
    stage = st.session_state.get("mi_stage", "setup")

    if stage == "interview" and st.session_state.get("mi_questions"):
        _interview_stage()
    elif stage == "result" and st.session_state.get("mi_report"):
        _result_stage()
    else:
        _setup_stage()