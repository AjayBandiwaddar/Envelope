"""
Day 1 infrastructure smoke tests.

These exist to satisfy CODEX_EXECUTION_PLAN.md's Day 1 requirement that
"pytest starts successfully" and that the health/readiness endpoints work,
using pytest-django's APIClient against the test settings (in-memory SQLite,
per config/settings/test.py, so this does not require Docker/PostgreSQL to
be running). Domain/policy tests begin on Day 2.
"""

import pytest
from rest_framework.test import APIClient


@pytest.mark.django_db
def test_health_endpoint_returns_ok():
    client = APIClient()
    response = client.get("/api/health/")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.django_db
def test_ready_endpoint_reports_database_status():
    client = APIClient()
    response = client.get("/api/ready/")
    # Redis may or may not be reachable in the environment this test runs in;
    # what we assert here is the *shape* and the database dependency, since
    # the test database (SQLite, in-memory) is always available under
    # pytest-django. Readiness behavior against a real, reachable Redis is
    # verified manually in the Day 1 report, not by this automated test.
    body = response.json()
    assert "dependencies" in body
    assert "database" in body["dependencies"]
    assert body["dependencies"]["database"] == "ok"
    assert response.status_code in (200, 503)
