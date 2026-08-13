"""
URL configuration for the Agent Action Firewall backend.

All API endpoints are namespaced under /api/, per API_SPEC.md §2.
Domain-specific routes are included from each app's own urls.py once
implemented (Day 2/3); Day 1 only wires up the cross-cutting health and
readiness endpoints required by API_SPEC.md §18-19.
"""

from django.contrib import admin
from django.urls import path

from config.health import health_view, ready_view

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/health/", health_view, name="health"),
    path("api/ready/", ready_view, name="ready"),
]
