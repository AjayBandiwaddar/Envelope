import pytest

from apps.agents.models import Agent, AgentStatus


@pytest.mark.django_db
def test_agent_created_active_by_default():
    agent = Agent.objects.create(agent_id="agent-001", name="Test Agent")
    assert agent.status == AgentStatus.ACTIVE
    assert agent.is_active() is True


@pytest.mark.django_db
def test_agent_token_is_never_stored_in_plaintext():
    agent = Agent.objects.create(agent_id="agent-002", name="Test Agent")
    raw_token = agent.issue_token()

    agent.refresh_from_db()
    assert agent.token_hash != raw_token
    assert agent.token_hash == Agent.hash_token(raw_token)


@pytest.mark.django_db
def test_disabled_agent_is_not_active():
    agent = Agent.objects.create(
        agent_id="agent-003", name="Disabled Agent", status=AgentStatus.DISABLED
    )
    assert agent.is_active() is False


@pytest.mark.django_db
def test_agent_id_must_be_unique():
    Agent.objects.create(agent_id="agent-004", name="First")
    with pytest.raises(Exception):
        Agent.objects.create(agent_id="agent-004", name="Duplicate")
