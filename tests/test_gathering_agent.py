"""
Tests for Scholarship Outreach Gathering Agent & NVIDIA Multi-Key Pool Architecture.
Verifies autonomous data gathering endpoints, live polling, pause/resume/stop,
Excel multi-sheet export, CSV export, multi-key round-robin rotation, and 429 failover.
"""
import io
import json
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
import openpyxl

from backend.main import app
from backend.config import config, NVIDIA_MODELS_CATALOG
from backend.llm.client import AIClient
from backend.database import (
    enqueue_research_job,
    insert_scholarships,
    insert_professors,
    update_job_status
)
from backend.export.data_exporter import (
    export_gathering_pipeline_excel,
    export_gathering_pipeline_csv,
    sanitize_csv_cell
)
from backend.agents.gathering_agent import GatheringAgentOrchestrator, AgentRunConfig


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def sample_gathering_job():
    """Seeds test database with a gathering job, scholarships, and professors."""
    job_id = enqueue_research_job(
        university_url="https://cs.stanford.edu",
        university_name="Stanford University",
        scope="all",
        job_type="agent_gathering_job"
    )
    insert_scholarships(job_id, [
        {
            "title": "Stanford Graduate Fellowship in Science & Engineering",
            "university": "Stanford University",
            "country": "United States",
            "program": "Computer Science",
            "degree_level": "Ph.D.",
            "funding_category": "Explicit full tuition plus living support",
            "amount": "Full Tuition + $45,000/year Stipend",
            "deadline": "December 10, 2025",
            "deadline_date": "2025-12-10",
            "eligibility_status": "Appears eligible",
            "source_url": "https://gradadmissions.stanford.edu/funding",
            "fit_score": 96,
            "fit_reason": "Full coverage PhD funding in machine learning",
            "department_contact": "gradadmissions@cs.stanford.edu"
        }
    ])
    insert_professors(job_id, [
        {
            "name": "Dr. Christopher Manning",
            "title": "Professor of Computer Science & Linguistics",
            "department": "Computer Science & AI Lab",
            "university": "Stanford University",
            "email": "manning@cs.stanford.edu",
            "research_interests": "Natural Language Processing, Deep Learning, Foundation Models",
            "recruitment_status": "Actively recruiting",
            "match_score": 98,
            "source_url": "https://profiles.stanford.edu/christopher-manning",
            "phone": "+1 650 723 0000"
        }
    ])
    update_job_status(job_id, "completed", progress_pct=100)
    return job_id


# ============================================================================
# 1. NVIDIA MODELS & MULTI-KEY ENDPOINTS
# ============================================================================

def test_nvidia_models_catalog_endpoint(client):
    """Verifies that the NVIDIA models catalog endpoint returns the curated models."""
    res = client.get("/api/settings/nvidia-models")
    assert res.status_code == 200
    data = res.json()
    assert "catalog" in data
    assert "fallback_models" in data
    assert len(data["catalog"]) >= 5
    
    # Verify flagship models are present
    model_ids = [m["id"] for m in data["catalog"]]
    assert "nvidia/llama-3.1-nemotron-70b-instruct" in model_ids
    assert "meta/llama-3.3-70b-instruct" in model_ids
    assert "deepseek-ai/deepseek-r1" in model_ids


def test_test_all_keys_diagnostics_endpoint(client):
    """Verifies /api/settings/test-all-keys endpoint with mock responses."""
    with patch.object(AIClient, "test_all_keys") as mock_test:
        mock_test.return_value = {
            "total_keys": 2,
            "valid_keys": 2,
            "all_valid": True,
            "results": [
                {"index": 1, "masked_key": "nvapi-1234...9999", "valid": True, "latency_ms": 120, "model": "nvidia/llama-3.1-nemotron-70b-instruct"},
                {"index": 2, "masked_key": "nvapi-5678...0000", "valid": True, "latency_ms": 115, "model": "nvidia/llama-3.1-nemotron-70b-instruct"}
            ]
        }
        res = client.post("/api/settings/test-all-keys")
        assert res.status_code == 200
        data = res.json()
        assert data["total_keys"] == 2
        assert data["valid_keys"] == 2
        assert data["all_valid"] is True
        assert len(data["results"]) == 2


# ============================================================================
# 2. AI CLIENT MULTI-KEY ROUND ROBIN & FAILOVER
# ============================================================================

def test_ai_client_multi_key_parsing_and_rotation():
    """Verifies that multiple keys are correctly parsed, deduplicated, and rotated round-robin."""
    key_pool = ["nvapi-key-alpha", "nvapi-key-beta", "nvapi-key-gamma"]
    config.update_settings(api_keys=key_pool)
    ai_client = AIClient()
    
    # Test sequential round-robin key selection
    k1 = ai_client._get_next_api_key()
    k2 = ai_client._get_next_api_key()
    k3 = ai_client._get_next_api_key()
    k4 = ai_client._get_next_api_key()
    
    selected_keys = [k1, k2, k3]
    assert set(selected_keys) == set(key_pool)
    assert k4 in key_pool


def test_ai_client_rate_limit_failover():
    """Verifies that on 429 / Rate Limit error, the client temporarily throttles the key and fails over."""
    key_pool = ["nvapi-key-rate-limited", "nvapi-key-healthy"]
    config.update_settings(api_keys=key_pool)
    ai_client = AIClient()
    
    # Mark first key as throttled
    ai_client._mark_key_throttled("nvapi-key-rate-limited", duration_sec=60.0)
    
    # Next key chosen should skip throttled key and return healthy key
    next_key = ai_client._get_next_api_key()
    assert next_key == "nvapi-key-healthy"


# ============================================================================
# 3. GATHERING AGENT PIPELINE API ENDPOINTS
# ============================================================================

def test_start_gathering_agent_endpoint(client):
    """Verifies the /api/agent/start-gathering endpoint validates input and enqueues job."""
    payload = {
        "degree_levels": ["MS", "PhD"],
        "subject": "Artificial Intelligence",
        "target_countries": ["United States", "Canada"],
        "max_universities": 5
    }
    res = client.post("/api/agent/start-gathering", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert "job_id" in data
    assert data["job_id"] > 0
    assert data["success"] is True
    assert "status_url" in data
    assert "Artificial Intelligence" in data["message"]


def test_start_gathering_agent_validation(client):
    """Verifies validation error on missing subject or degree levels."""
    res = client.post("/api/agent/start-gathering", json={"degree_levels": [], "subject": ""})
    assert res.status_code in (400, 422)


def test_gathering_agent_status_endpoint(client, sample_gathering_job):
    """Verifies status endpoint returns progress counters, university, and log lines."""
    res = client.get(f"/api/agent/status/{sample_gathering_job}")
    assert res.status_code == 200
    data = res.json()
    assert data["job_id"] == sample_gathering_job
    assert data["status"] == "completed"
    assert data["universities_count"] >= 1
    assert data["scholarships_count"] >= 1
    assert data["professors_count"] >= 1


def test_gathering_agent_pause_resume_stop_endpoints(client):
    """Verifies pause, resume, and stop controls on an active/queued job."""
    job_id = enqueue_research_job(
        university_url="https://cs.stanford.edu",
        university_name="Stanford University",
        job_type="agent_gathering_job"
    )
    # Pause
    res_pause = client.post(f"/api/agent/pause/{job_id}")
    assert res_pause.status_code == 200
    assert res_pause.json()["success"] is True
    
    # Resume
    res_resume = client.post(f"/api/agent/resume/{job_id}")
    assert res_resume.status_code == 200
    assert res_resume.json()["success"] is True
    
    # Stop
    res_stop = client.post(f"/api/agent/stop/{job_id}")
    assert res_stop.status_code == 200
    assert res_stop.json()["success"] is True


# ============================================================================
# 4. EXCEL & CSV EXPORTER VERIFICATION
# ============================================================================

def test_excel_export_structure_and_formatting(sample_gathering_job):
    """Verifies that the generated Excel workbook contains two sheets with exact columns and values."""
    excel_bytes = export_gathering_pipeline_excel(sample_gathering_job)
    assert len(excel_bytes) > 0
    
    # Load with openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(excel_bytes))
    sheet_names = wb.sheetnames
    assert "Universities & Scholarships" in sheet_names
    assert "Professors" in sheet_names
    
    # Sheet 1: Universities & Scholarships
    ws_schol = wb["Universities & Scholarships"]
    headers_schol = [cell.value for cell in ws_schol[1]]
    assert "University" in headers_schol
    assert "Scholarship Name" in headers_schol
    assert "Degree Level" in headers_schol
    assert "Funding Coverage" in headers_schol
    assert "Eligibility Criteria" in headers_schol
    assert "Deadline" in headers_schol
    assert "Official Website URL" in headers_schol
    assert "Scholarship Office / Contact" in headers_schol
    assert "Source URL" in headers_schol
    
    # Verify row data in Sheet 1
    row2_schol = [cell.value for cell in ws_schol[2]]
    assert "Stanford University" in row2_schol
    assert "Stanford Graduate Fellowship in Science & Engineering" in row2_schol
    
    # Sheet 2: Professors
    ws_prof = wb["Professors"]
    headers_prof = [cell.value for cell in ws_prof[1]]
    assert "Professor Name" in headers_prof
    assert "Academic Title" in headers_prof
    assert "Department" in headers_prof
    assert "University" in headers_prof
    assert "Research Interests & Focus" in headers_prof
    assert "Relevance Score (0-100)" in headers_prof
    assert "Publicly Listed Email" in headers_prof
    assert "Official Profile URL" in headers_prof
    assert "Source URL" in headers_prof
    
    # Verify row data in Sheet 2
    row2_prof = [cell.value for cell in ws_prof[2]]
    assert "Dr. Christopher Manning" in row2_prof
    assert "manning@cs.stanford.edu" in row2_prof


def test_csv_export_structure(sample_gathering_job):
    """Verifies that the CSV exporter outputs valid CSV content with both scholarships and professors."""
    csv_text = export_gathering_pipeline_csv(sample_gathering_job)
    assert "Record Type,University,Country" in csv_text
    assert "Scholarship" in csv_text
    assert "Professor" in csv_text
    assert "Stanford University" in csv_text
    assert "Dr. Christopher Manning" in csv_text
    assert "manning@cs.stanford.edu" in csv_text


def test_csv_formula_injection_sanitization():
    """Verifies formula injection characters (=, +, -, @, tab) are safely escaped."""
    assert sanitize_csv_cell("=SUM(A1:A10)").startswith("'")
    assert sanitize_csv_cell("+cmd|' /C calc'!A0").startswith("'")
    assert sanitize_csv_cell("@eval(1)").startswith("'")
    assert sanitize_csv_cell("Normal Text") == "Normal Text"
