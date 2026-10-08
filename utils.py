"""
utils.py
--------
Utility functions for the AI Career Assistant.

Handles:
- PDF text extraction
- Analysis history conversion
- Excel export
- CSV export
"""

import io
import pandas as pd
from pypdf import PdfReader


# -------------------------------------------------------------------
# PDF TEXT EXTRACTION
# -------------------------------------------------------------------

def extract_text_from_pdf(uploaded_file) -> str:
    """
    Extract readable text from an uploaded PDF.

    Works with Streamlit UploadedFile objects.
    """

    try:
        if uploaded_file is None:
            raise ValueError("No PDF file was uploaded.")

        # Read uploaded file safely
        pdf_bytes = uploaded_file.getvalue()

        if not pdf_bytes:
            raise ValueError("The uploaded PDF is empty.")

        # Basic PDF validation
        if not pdf_bytes.startswith(b"%PDF"):
            raise ValueError(
                "The uploaded file does not appear to be a valid PDF."
            )

        # Read PDF from memory
        pdf_stream = io.BytesIO(pdf_bytes)

        reader = PdfReader(
            pdf_stream,
            strict=False
        )

        if len(reader.pages) == 0:
            raise ValueError("The PDF contains no pages.")

        text_parts = []

        for page_number, page in enumerate(reader.pages, start=1):

            try:
                page_text = page.extract_text() or ""

                if page_text.strip():
                    text_parts.append(page_text.strip())

            except Exception:
                # Skip problematic pages instead of crashing
                continue

        text = "\n\n".join(text_parts).strip()

        if not text:
            raise ValueError(
                "No readable text was found in this PDF. "
                "If this is a scanned/image-based resume, "
                "please upload a text-based PDF."
            )

        return text

    except ValueError:
        raise

    except Exception as e:
        raise ValueError(
            f"Unable to read the PDF. Details: {e}"
        )


# -------------------------------------------------------------------
# ANALYSIS DATAFRAME
# -------------------------------------------------------------------

def analyses_to_dataframe(analyses: list) -> pd.DataFrame:
    """
    Convert saved analysis records into a clean DataFrame.

    Keeps the columns currently used by the History section.
    """

    if not analyses:
        return pd.DataFrame(
            columns=[
                "Job Title",
                "Match %",
                "Summary",
            ]
        )

    rows = []

    for analysis in analyses:

        if not isinstance(analysis, dict):
            continue

        rows.append(
            {
                "Job Title": analysis.get(
                    "job_title",
                    ""
                ),

                "Match %": analysis.get(
                    "match_percentage",
                    ""
                ),

                "Summary": analysis.get(
                    "summary",
                    ""
                ),
            }
        )

    return pd.DataFrame(
        rows,
        columns=[
            "Job Title",
            "Match %",
            "Summary",
        ]
    )


# -------------------------------------------------------------------
# EXCEL EXPORT
# -------------------------------------------------------------------

def export_to_excel_bytes(analyses: list) -> bytes:
    """
    Convert analysis history into an Excel (.xlsx) file
    and return it as bytes.

    This is suitable for Streamlit st.download_button().
    """

    df = analyses_to_dataframe(analyses)

    output = io.BytesIO()

    with pd.ExcelWriter(
        output,
        engine="openpyxl"
    ) as writer:

        df.to_excel(
            writer,
            index=False,
            sheet_name="Analysis History"
        )

        # Get worksheet for basic formatting
        worksheet = writer.sheets["Analysis History"]

        # Freeze header row
        worksheet.freeze_panes = "A2"

        # Make columns readable
        worksheet.column_dimensions["A"].width = 25
        worksheet.column_dimensions["B"].width = 12
        worksheet.column_dimensions["C"].width = 80

        # Add filter to header
        if not df.empty:
            worksheet.auto_filter.ref = worksheet.dimensions

    output.seek(0)

    return output.getvalue()


# -------------------------------------------------------------------
# BACKWARD COMPATIBILITY
# -------------------------------------------------------------------

def export_to_csv_bytes(analyses: list) -> bytes:
    """
    Backward-compatible export function.

    IMPORTANT:
    The existing app.py currently calls this function but downloads
    the result as an .xlsx file.

    Therefore this function intentionally returns Excel bytes rather
    than CSV bytes, so the existing app.py continues to work correctly.
    """

    return export_to_excel_bytes(analyses)


# -------------------------------------------------------------------
# TRUE CSV EXPORT
# -------------------------------------------------------------------

def export_to_true_csv_bytes(analyses: list) -> bytes:
    """
    Export analysis history as an actual CSV file.

    Useful if CSV download is needed later.
    """

    df = analyses_to_dataframe(analyses)

    return df.to_csv(
        index=False
    ).encode("utf-8-sig")