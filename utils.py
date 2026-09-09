import io
import pandas as pd
from pypdf import PdfReader


def extract_text_from_pdf(uploaded_file) -> str:
    """Extract text from uploaded PDF."""

    try:
        pdf_bytes = uploaded_file.getvalue()

        if not pdf_bytes:
            raise ValueError("The uploaded PDF is empty.")

        if not pdf_bytes.startswith(b"%PDF"):
            raise ValueError("The uploaded file is not a valid PDF.")

        pdf_stream = io.BytesIO(pdf_bytes)
        reader = PdfReader(pdf_stream, strict=False)

        text_parts = []

        for page in reader.pages:
            text_parts.append(page.extract_text() or "")

        text = "\n".join(text_parts).strip()

        if not text:
            raise ValueError(
                "No readable text found. This may be a scanned PDF."
            )

        return text

    except Exception as e:
        raise ValueError(f"Unable to read this PDF. Details: {e}")


def analyses_to_dataframe(analyses: list) -> pd.DataFrame:
    """Convert saved analyses into a pandas DataFrame."""

    if not analyses:
        return pd.DataFrame()

    rows = []

    for analysis in analyses:
        rows.append({
            "Job Title": analysis.get("job_title", ""),
            "Match %": analysis.get("match_percentage", ""),
            "Summary": analysis.get("summary", ""),
        })

    return pd.DataFrame(rows)