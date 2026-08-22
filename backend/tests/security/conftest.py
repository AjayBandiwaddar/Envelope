import pytest

from apps.tools.models import Tool


@pytest.fixture
def delete_customer_tool(db):
    return Tool.objects.create(tool_id="delete_customer", name="Delete Customer")


@pytest.fixture
def get_order_tool(db):
    return Tool.objects.create(tool_id="get_order", name="Get Order")