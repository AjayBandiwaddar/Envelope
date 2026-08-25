"""
URL configuration for the Agent Action Firewall backend.

All API endpoints are namespaced under /api/, per API_SPEC.md Section 2.
Note what is deliberately NOT here: there is no
/api/internal/tools/{tool_id}/execute/ route anywhere in this file. Per
docs/SPEC_REVIEW.md Section 3.4, tool execution
(apps.tools.gateway.execute_tool) is an internal Python function call,
never a reachable URL - see THREAT_MODEL.md Section 5.14 and its
structural test in tests/security/.
"""

from django.contrib import admin
from django.urls import include, path

from config.health import health_view, ready_view

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("apps.commerce.urls")),
    path("api/health/", health_view, name="health"),
    path("api/ready/", ready_view, name="ready"),
    path("api/agents/", include("apps.agents.urls")),
    path("api/tasks/", include("apps.tasks.urls")),
    path("api/policies/", include("apps.policies.urls")),
    path("api/tools/", include("apps.tools.urls")),
    path("api/audit-events/", include("apps.audit.urls")),
    path("api/", include("apps.authorization.urls")),
]