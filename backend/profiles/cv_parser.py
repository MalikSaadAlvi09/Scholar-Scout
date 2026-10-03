"""
CV Document Parser & Fact Extractor for ScholarScout.
Extracts text from PDF and DOCX files safely.
Detects scanned/image-only PDFs, unsupported formats, and extracts proposed profile facts
for human review before merging into the academic profile.
Preserves original GPA scales without automatic conversion.
"""

import io
import re
import zipfile
import xml.etree.ElementTree as ET
from typing import Dict, Any, Optional, List, Tuple
from pydantic import BaseModel, Field

try:
    import fitz  # PyMuPDF
    HAS_FITZ = True
except ImportError:
    HAS_FITZ = False

from backend.llm.client import ai_client
from backend.llm.security import frame_untrusted_content
from backend.logging_utils import logger

class ProposedProfileFacts(BaseModel):
    """Structured facts extracted from CV for human review and confirmation."""
    full_name: Optional[str] = Field(None, description="Candidate full name")
    nationality: Optional[str] = Field(None, description="Citizenship or nationality if stated")
    current_residence: Optional[str] = Field(None, description="Current country/city of residence")
    current_degree: Optional[str] = Field(None, description="Current or most recent degree (e.g. B.S. in Computer Science)")
    current_institution: Optional[str] = Field(None, description="Current or graduated university")
    gpa: Optional[str] = Field(None, description="Original GPA with scale preserved (e.g. 3.9/4.0, 8.8/10.0, First Class)")
    graduation_date: Optional[str] = Field(None, description="Graduation or expected graduation date")
    target_degree: Optional[str] = Field(None, description="Target degree if indicated (e.g. Ph.D., Master's)")
    broad_subject: Optional[str] = Field(None, description="Primary field of study (e.g. Computer Science)")
    specific_interests: Optional[str] = Field(None, description="Specific research areas and topics")
    english_tests: Optional[str] = Field(None, description="English language test scores (TOEFL, IELTS, etc.)")
    projects: Optional[str] = Field(None, description="Key projects mentioned")
    publications: Optional[str] = Field(None, description="Publications, preprints, conference papers")
    research_experience: Optional[str] = Field(None, description="Research assistantships or lab work")
    technical_skills: Optional[str] = Field(None, description="Programming languages, frameworks, tools")
    background_summary: Optional[str] = Field(None, description="Concise 2-3 sentence academic summary")
    github_url: Optional[str] = Field(None, description="GitHub profile URL")
    portfolio_url: Optional[str] = Field(None, description="Portfolio or project website URL")
    website_url: Optional[str] = Field(None, description="Personal homepage or LinkedIn URL")

CV_EXTRACTION_SYSTEM_PROMPT = """You are an academic CV analysis assistant for ScholarScout.
Extract factual information from the candidate's CV text into the requested JSON schema for their academic profile.

CRITICAL EXTRACTION CONSTRAINTS:
1. ONLY extract information that is explicitly stated in the CV.
2. DO NOT invent, fabricate, guess, or extrapolate missing details.
3. PRESERVE ORIGINAL GPA AND GRADING SCALES:
   - Never convert GPA to a 4.0 scale if given in 10.0, 100%, percentages, or division honors.
   - Keep exact strings like "3.92/4.0", "8.75/10.0", "88%", "First Class with Distinction".
4. DO NOT declare degree equivalences.
5. If a field is not present in the CV, return null (do not write 'Unknown' or fabricate).
6. Return only valid JSON matching the schema.
"""

def extract_text_from_pdf(file_bytes: bytes) -> Tuple[bool, str, Optional[str]]:
    """
    Extracts text from PDF using PyMuPDF.
    Detects scanned/image-only PDFs and returns user-friendly error messages.
    """
    if not HAS_FITZ:
        return False, "", "PDF extraction library (PyMuPDF) is not installed."

    try:
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        total_pages = len(doc)
        if total_pages == 0:
            return False, "", "The uploaded PDF document contains no pages."

        full_text = []
        has_images = False

        for page_num in range(total_pages):
            page = doc[page_num]
            text = page.get_text()
            if text and text.strip():
                full_text.append(text.strip())
            if len(page.get_images()) > 0:
                has_images = True

        combined_text = "\n\n".join(full_text).strip()

        # Check if scanned/empty
        if len(combined_text) < 50:
            if has_images:
                return False, "", "Scanned image-only PDF detected without selectable text. Please upload a searchable digital PDF or Word (.docx) document, or enter details manually."
            else:
                return False, "", "The uploaded PDF does not contain extractable text."

        return True, combined_text, None

    except Exception as e:
        logger.error(f"[CV Parser] PDF extraction failed: {e}")
        return False, "", f"Could not parse PDF file: {str(e)}"

def extract_text_from_docx(file_bytes: bytes) -> Tuple[bool, str, Optional[str]]:
    """
    Extracts text from DOCX by parsing word/document.xml inside zip archive.
    """
    try:
        with zipfile.ZipFile(io.BytesIO(file_bytes)) as z:
            if "word/document.xml" not in z.namelist():
                return False, "", "Invalid DOCX format: word/document.xml not found."

            xml_content = z.read("word/document.xml")
            tree = ET.fromstring(xml_content)

            # Namespace for WordprocessingML
            ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}

            paragraphs = []
            for p in tree.iter(f"{{{ns['w']}}}p"):
                texts = [node.text for node in p.iter(f"{{{ns['w']}}}t") if node.text]
                if texts:
                    paragraphs.append("".join(texts))

            combined = "\n".join(paragraphs).strip()
            if len(combined) < 30:
                return False, "", "The uploaded DOCX document contains insufficient or empty text."

            return True, combined, None

    except Exception as e:
        logger.error(f"[CV Parser] DOCX extraction failed: {e}")
        return False, "", f"Could not parse DOCX file: {str(e)}"

def heuristic_cv_extractor(cv_text: str) -> Dict[str, Any]:
    """
    Offline/Rule-based CV parser that extracts candidate facts safely without AI,
    preserving exact GPA scales and marking missing fields as None.
    """
    lines = [l.strip() for l in cv_text.split("\n") if l.strip()]
    facts: Dict[str, Any] = {}

    # 1. Candidate Name (usually on the first 3 lines)
    for line in lines[:3]:
        clean = re.sub(r'[^a-zA-Z\s\.\-]', '', line).strip()
        words = clean.split()
        if 2 <= len(words) <= 4 and not any(kw in clean.lower() for kw in ["curriculum", "resume", "cv", "page", "email", "phone"]):
            facts["full_name"] = clean
            break

    # 2. Links
    github_match = re.search(r'https?://(?:www\.)?github\.com/[A-Za-z0-9_\-]+', cv_text, re.I)
    if github_match:
        facts["github_url"] = github_match.group(0)

    website_match = re.search(r'https?://(?:www\.)?[a-zA-Z0-9\.\-_]+\.(?:io|me|dev|org|edu|com)(?:/[^\s]*)?', cv_text, re.I)
    if website_match and ("github.com" not in website_match.group(0)):
        facts["website_url"] = website_match.group(0)

    # 3. GPA with original scale
    gpa_match = re.search(r'(?:GPA|CGPA|Grade|Average)[\s:]*([0-9\.]+\s*(?:\/\s*[0-9\.]+|%|\s*out of\s*[0-9\.]+)?|First Class[^\n,]*)', cv_text, re.I)
    if gpa_match:
        facts["gpa"] = gpa_match.group(1).strip()

    # 4. Degree & Institution
    deg_match = re.search(r'(Bachelor(?:[\'’]s)?|Master(?:[\'’]s)?|B\.?S\.?|M\.?S\.?|B\.?Tech|M\.?Tech|Ph\.?D\.?)\s+(?:of|in)?\s+([A-Za-z\s]+)', cv_text, re.I)
    if deg_match:
        facts["current_degree"] = f"{deg_match.group(1)} in {deg_match.group(2).strip()}".strip()

    uni_match = re.search(r'(University of [A-Za-z\s]+|[A-Za-z\s]+ University|[A-Za-z\s]+ Institute of Technology)', cv_text, re.I)
    if uni_match:
        facts["current_institution"] = uni_match.group(1).strip()

    # 5. English tests
    toefl_match = re.search(r'(TOEFL[^\n,;]+)', cv_text, re.I)
    ielts_match = re.search(r'(IELTS[^\n,;]+)', cv_text, re.I)
    if toefl_match:
        facts["english_tests"] = toefl_match.group(1).strip()
    elif ielts_match:
        facts["english_tests"] = ielts_match.group(1).strip()

    # 6. Skills section
    skills_match = re.search(r'(?:Technical Skills|Skills|Technologies)[\s:]*([^\n]+(?:\n[^\n]+){1,4})', cv_text, re.I)
    if skills_match:
        facts["technical_skills"] = skills_match.group(1).strip()

    # 7. Publications
    pub_match = re.search(r'(?:Publications|Papers|Preprints)[\s:]*([^\n]+(?:\n[^\n]+){1,5})', cv_text, re.I)
    if pub_match:
        facts["publications"] = pub_match.group(1).strip()

    # 8. Research Experience
    research_match = re.search(r'(?:Research Experience|Research Experience & Projects|Academic Research)[\s:]*([^\n]+(?:\n[^\n]+){1,5})', cv_text, re.I)
    if research_match:
        facts["research_experience"] = research_match.group(1).strip()

    # 9. Background summary from top
    facts["background_summary"] = " ".join(lines[:4])[:300]

    return facts

async def extract_facts_from_cv(
    filename: str,
    file_bytes: bytes
) -> Dict[str, Any]:
    """
    Parses an uploaded CV file (.pdf or .docx) and extracts proposed profile facts.
    Returns status, extracted raw text, and structured proposed facts for user confirmation.
    """
    fn_lower = filename.lower()
    success = False
    text = ""
    error_msg = None

    if fn_lower.endswith(".pdf"):
        success, text, error_msg = extract_text_from_pdf(file_bytes)
    elif fn_lower.endswith(".docx"):
        success, text, error_msg = extract_text_from_docx(file_bytes)
    else:
        return {
            "success": False,
            "error_type": "unsupported_format",
            "message": f"Unsupported file type for '{filename}'. Please upload a PDF (.pdf) or Word document (.docx)."
        }

    if not success or not text:
        return {
            "success": False,
            "error_type": "extraction_error",
            "message": error_msg or "Failed to extract text from document."
        }

    # Extract structured facts
    proposed_facts: Dict[str, Any] = {}

    if ai_client.is_configured():
        try:
            framed_cv = frame_untrusted_content(text[:9000], source_url=filename, content_type="uploaded_cv_document")
            user_prompt = f"""File Name: {filename}

{framed_cv}

Extract all verifiable academic profile facts into the required JSON schema. Mark unmentioned fields as null. Preserve GPA and grading scales verbatim."""

            result = await ai_client.generate_structured(
                schema=ProposedProfileFacts,
                system_prompt=CV_EXTRACTION_SYSTEM_PROMPT,
                user_prompt=user_prompt
            )
            if result.data:
                # Filter out None values to only return extracted facts
                for k, v in result.data.model_dump().items():
                    if v is not None and str(v).strip():
                        proposed_facts[k] = v
        except Exception as e:
            logger.warning(f"[CV Parser] AI fact extraction failed: {e}. Falling back to heuristic parser.")

    # Fallback to heuristic parser if AI returned empty or failed
    if not proposed_facts:
        proposed_facts = heuristic_cv_extractor(text)

    return {
        "success": True,
        "filename": filename,
        "text_length": len(text),
        "proposed_facts": proposed_facts,
        "message": f"Successfully parsed '{filename}' and extracted {len(proposed_facts)} candidate facts. Please review and confirm before merging into your profile."
    }
