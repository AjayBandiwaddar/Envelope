"""
Runs the MCP tool server over stdio, for use with MCP-compatible
clients (Claude Desktop, Claude Code, etc.).

Usage: python manage.py run_mcp_server
"""

import anyio
from django.core.management.base import BaseCommand

from apps.tools.mcp_server import mcp_server


class Command(BaseCommand):
    help = "Run the Agent Action Firewall MCP server over stdio."

    def handle(self, *args, **options):
        anyio.run(mcp_server.run_stdio_async)