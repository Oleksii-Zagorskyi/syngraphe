from django.urls import path

from audit import views

urlpatterns = [
    path("administration/platform/audit/", views.audit_log, name="audit_log"),
]
