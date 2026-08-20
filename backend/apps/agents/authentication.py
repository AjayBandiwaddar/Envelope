"""
Agent bearer-token authentication.

Per docs/SPEC_REVIEW.md Section 3.1 and API_SPEC.md Section 3: an agent's
execution-time identity must be established from its authenticated
credential, never trusted from a request-body `agent_id` field. This
class resolves the token to an Agent row and exposes it as the
authenticated principal; callers must still separately check that any
agent_id in the request body matches this authenticated identity before
using it (apps/authorization/views.py does this).
"""

from rest_framework import authentication, exceptions

from .models import Agent


class AuthenticatedAgent:
    """
    Lightweight authenticated-principal wrapper. Not a Django User - the
    authorization endpoint has no notion of a Django user account, only
    of registered Agents. DRF's IsAuthenticated permission only needs
    `.is_authenticated` to be truthy.
    """

    is_authenticated = True
    is_admin = False

    def __init__(self, agent: Agent):
        self.agent = agent

    @property
    def agent_id(self) -> str:
        return self.agent.agent_id


class AgentBearerTokenAuthentication(authentication.BaseAuthentication):
    """
    Authenticates a request via `Authorization: Bearer <token>` against
    the hashed tokens stored on Agent rows (Agent.hash_token /
    Agent.issue_token). Disabled agents authenticate successfully here
    (the credential is valid) but are denied at the policy-evaluation
    layer with AGENT_DISABLED, per API_SPEC.md Section 12 ("disabled
    agent" is a 200/DENY authorization outcome, not a 401).
    """

    keyword = "Bearer"

    def authenticate(self, request):
        header = authentication.get_authorization_header(request).decode("utf-8")
        if not header:
            return None  # no credential supplied at all; let DRF's permission layer 401

        parts = header.split()
        if len(parts) != 2 or parts[0] != self.keyword:
            raise exceptions.AuthenticationFailed("Malformed Authorization header.")

        raw_token = parts[1]
        token_hash = Agent.hash_token(raw_token)

        try:
            agent = Agent.objects.get(token_hash=token_hash)
        except Agent.DoesNotExist:
            raise exceptions.AuthenticationFailed("Invalid agent credential.")

        return (AuthenticatedAgent(agent), raw_token)

    def authenticate_header(self, request):
        # Per API_SPEC.md Section 12 ("Missing agent identity" -> HTTP
        # 401): DRF only returns 401 (vs. its 403 default) when the
        # authentication class defines this method.
        return self.keyword


class AdminTokenAuthentication(authentication.BaseAuthentication):
    """
    Simple shared-secret authentication for administrative endpoints
    (create/modify agents, tasks, policies, tools). Deliberately a
    distinct credential type from AgentBearerTokenAuthentication -
    per THREAT_MODEL.md Section 5.13, an agent's execution token must
    never be usable to call administrative endpoints, and vice versa.

    Week 1 simplification: a single shared admin token from settings,
    not per-user accounts (AGENTS.md Non-Goals explicitly excludes
    enterprise SSO). Documented in .env.example.
    """

    keyword = "Bearer"

    class AdminPrincipal:
        is_authenticated = True
        is_admin = True

    def authenticate(self, request):
        from django.conf import settings

        header = authentication.get_authorization_header(request).decode("utf-8")
        if not header:
            return None

        parts = header.split()
        if len(parts) != 2 or parts[0] != self.keyword:
            raise exceptions.AuthenticationFailed("Malformed Authorization header.")

        raw_token = parts[1]
        expected = getattr(settings, "ADMIN_API_TOKEN", "")
        if not expected or raw_token != expected:
            raise exceptions.AuthenticationFailed("Invalid admin credential.")

        return (self.AdminPrincipal(), raw_token)

    def authenticate_header(self, request):
        return self.keyword