from django.conf import settings
from rest_framework.routers import DefaultRouter, SimpleRouter

from intentions_page.api.views import (
    IntentionViewSet,
    IntentionsDraftViewSet,
    NoteViewSet,
    RecurringIntentionViewSet,
)
from intentions_page.users.api.views import UserViewSet

if settings.DEBUG:
    router = DefaultRouter()
else:
    router = SimpleRouter()

router.register("users", UserViewSet)
router.register("intentions", IntentionViewSet, basename="intention")
router.register("notes", NoteViewSet, basename="note")
router.register("drafts", IntentionsDraftViewSet, basename="draft")
router.register("recurring", RecurringIntentionViewSet, basename="recurring")


app_name = "api"
urlpatterns = router.urls
