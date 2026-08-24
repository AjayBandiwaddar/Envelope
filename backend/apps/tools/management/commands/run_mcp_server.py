"""
Runs the MCP tool server over stdio, for use with MCP-compatible
clients (Claude Desktop, Claude Code, etc.).

Usage: python manage.py run_mcp_server
"""

import os
import anyio
from django.core.management.base import BaseCommand, CommandError
from apps.tools.mcp_server import mcp_server
class Command(BaseCommand):
    help = "Run the Agent Action Firewall MCP server over stdio."
    def handle(self, *args, **options):
        if not os.environ.get("AGENT_TOKEN"):
            raise CommandError("AGENT_TOKEN environment variable must be set before starting the MCP server.")
        anyio.run(mcp_server.run_stdio_async)