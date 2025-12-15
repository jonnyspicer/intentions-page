import pytest

from intentions_page.users.models import User

pytestmark = pytest.mark.django_db


def test_user_get_absolute_url(user: User):
    assert user.get_absolute_url() == f"/users/{user.username}/"


def test_user_show_tool_confirmations_default():
    """New users should have show_tool_confirmations=True by default."""
    user = User.objects.create(
        username="testuser",
        email="test@example.com"
    )
    assert user.show_tool_confirmations is True
