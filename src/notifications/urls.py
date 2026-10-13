from django.urls import path

from notifications.views import detail, page

urlpatterns = [
    path("notifications/", page.page, name="notifications"),
    path("notifications/read-all/", page.read_all, name="notifications_read_all"),
    path("notifications/<uuid:pk>/", detail.detail, name="notification"),
]
