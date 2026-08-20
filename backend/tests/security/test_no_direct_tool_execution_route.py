"""
THREAT_MODEL.md Section 5.14 / TEST_PLAN.md Section 3.14: there must be
no reachable URL for direct tool execution. Tool execution
(apps.tools.gateway.execute_tool) is an internal Python function call
only - see docs/SPEC_REVIEW.md Section 3.4.
"""

import pytest


@pytest.mark.django_db
@pytest.mark.parametrize(
    "path",
    [
        "/api/internal/tools/refund_order/execute/",
        "/api/tools/refund_order/execute/",
        "/api/execute/",
    ],
)
def test_no_tool_execution_endpoint_is_routable(admin_client, path):
    """
    A 404 here proves the route doesn't exist at all - stronger than a
    401/403, which would imply the route exists but is merely guarded.
    """
    response = admin_client.post(path, {}, format="json")
    assert response.status_code == 404