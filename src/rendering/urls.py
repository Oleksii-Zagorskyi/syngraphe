from django.urls import path

from rendering import views

urlpatterns = [
    path("document/<int:number>/export/", views.export, name="document_export"),
    path("document/<int:number>/export/<str:job_id>/", views.export_status, name="export_status"),
    path(
        "document/<int:number>/export/<str:job_id>/download/",
        views.export_download,
        name="export_download",
    ),
]
