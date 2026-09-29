from django.urls import path

from notifications import views

urlpatterns = [
    path("notifications/<uuid:pk>/", views.detail, name="notification"),
]
