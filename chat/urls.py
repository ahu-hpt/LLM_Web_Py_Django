from django.urls import path

from . import views

urlpatterns = [
    path("", views.index, name="index"),
    path("settings/", views.settings_view, name="settings"),
    path("api/chat/", views.chat_api, name="chat_api"),
    path("api/test/", views.test_api, name="test_api"),
]
