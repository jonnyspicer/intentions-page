from django.urls import include, path
from . import views

urlpatterns = [
    path('',views.home, name='home'),
    path("promote_draft_to_intentions", views.promote_draft_to_intentions, name='promote_draft_to_intentions'),
    path("edit/<int:primary_key>", views.edit, name='edit'),
    path("append/<int:primary_key>", views.append, name='append'),
    path("history", views.history, name='history'),
    path("feedback", views.feedback, name='feedback'),
    path("privacy-policy", views.privacy_policy, name='privacy-policy'),
    path("note/<int:primary_key>", views.note),
    path("intentions_draft/<int:primary_key>", views.intentions_draft),
    path("chat/history", views.chat_history, name='chat_history'),
    path("chat/send", views.chat_send_message, name='chat_send'),
    path("chat/clear", views.chat_clear_history, name='chat_clear'),
]
