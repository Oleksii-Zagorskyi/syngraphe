from django.urls import path

from rendering import appendix, views

urlpatterns = [
    path("document/<int:number>/compare/", views.compare, name="document_compare"),
    path(
        "document/<int:number>/version/<str:version_number>/",
        views.historical,
        name="document_version",
    ),
    path(
        "document/<int:number>/version/<str:version_number>/export/",
        views.export,
        name="document_version_export",
    ),
    path(
        "document/<int:number>/version/<str:version_number>/attachment/<int:part>/",
        views.historical_attachment,
        name="document_version_attachment",
    ),
    path("document/<int:number>/export/", views.export, name="document_export"),
    path("document/<int:number>/export/<str:job_id>/", views.export_status, name="export_status"),
    path(
        "document/<int:number>/export/<str:job_id>/download/",
        views.export_download,
        name="export_download",
    ),
    path("compare/", views.compare_start, name="compare_start"),
    path(
        "document/<int:number>/appendix/<int:part>/",
        appendix.page,
        name="document_appendix",
    ),
]
