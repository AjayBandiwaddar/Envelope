import pytest

from apps.tools.models import Tool, ToolStatus


@pytest.mark.django_db
def test_tool_active_by_default():
    tool = Tool.objects.create(tool_id="tool-001", name="Get Order")
    assert tool.is_active() is True


@pytest.mark.django_db
def test_disabled_tool_is_not_active():
    tool = Tool.objects.create(
        tool_id="tool-002", name="Delete Customer", status=ToolStatus.DISABLED
    )
    assert tool.is_active() is False


@pytest.mark.django_db
def test_tool_id_must_be_unique():
    Tool.objects.create(tool_id="tool-003", name="First")
    with pytest.raises(Exception):
        Tool.objects.create(tool_id="tool-003", name="Duplicate")
