from django.urls import path

from notifications.views import detail, page
from review.views import notice_images

urlpatterns = [
    path("notifications/", page.page, name="notifications"),
    path("notifications/read-all/", page.read_all, name="notifications_read_all"),
    path("notifications/<uuid:pk>/", detail.detail, name="notification"),
    path(
        "notifications/<uuid:pk>/image/<str:name>/",
        notice_images.image,
        name="notification_image",
    ),
]
