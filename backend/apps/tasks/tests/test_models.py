from datetime import timedelta

import pytest
from django.utils import timezone

from apps.agents.models import Agent
from apps.tasks.models import Task, TaskStatus


@pytest.fixture
def agent(db):
    return Agent.objects.create(agent_id="agent-001", name="Test Agent")


@pytest.mark.django_db
def test_task_not_expired_before_expiry(agent):
    task = Task.objects.create(
        task_id="task-001",
        agent=agent,
        status=TaskStatus.ACTIVE,
        expires_at=timezone.now() + timedelta(minutes=30),
    )
    assert task.is_expired() is False


@pytest.mark.django_db
def test_task_expired_after_expiry_regardless_of_stored_status(agent):
    """
    Per POLICY_SPEC.md Section 19: time is checked server-side and
    independently of the stored status field, so a task whose status
    hasn't been lazily transitioned yet must still report expired.
    """
    task = Task.objects.create(
        task_id="task-002",
        agent=agent,
        status=TaskStatus.ACTIVE,  # deliberately not "EXPIRED"
        expires_at=timezone.now() - timedelta(minutes=1),
    )
    assert task.is_expired() is True


@pytest.mark.django_db
def test_task_id_must_be_unique(agent):
    Task.objects.create(
        task_id="task-003", agent=agent, expires_at=timezone.now() + timedelta(minutes=30)
    )
    with pytest.raises(Exception):
        Task.objects.create(
            task_id="task-003", agent=agent, expires_at=timezone.now() + timedelta(minutes=30)
        )


@pytest.mark.django_db
def test_task_requires_an_agent():
    with pytest.raises(Exception):
        Task.objects.create(
            task_id="task-004", expires_at=timezone.now() + timedelta(minutes=30)
        )
