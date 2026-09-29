from django.urls import path

from shell import views

urlpatterns = [
    path("", views.root, name="root"),
    path("health/", views.health, name="health"),
    path("administration/", views.administration, name="administration"),
    path("administration/organisation/", views.choose_organisation, name="choose_organisation"),
]
