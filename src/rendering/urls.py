from django.urls import path

from rendering import appendix, styles_views, views

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
    path(
        "document/<int:number>/version/<str:version_number>/appendix/<int:part>/",
        appendix.historical,
        name="document_version_appendix",
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
        "document/<int:number>/compare/appendix/",
        appendix.compare,
        name="document_compare_appendix",
    ),
    path(
        "document/<int:number>/appendix/<int:part>/",
        appendix.page,
        name="document_appendix",
    ),
    path("administration/tenant/styles/", styles_views.styles, name="styles"),
    path("administration/tenant/styles/sample/", styles_views.sample, name="styles_sample"),
    path(
        "administration/tenant/styles/sample/<uuid:sample_id>/",
        styles_views.sample_status,
        name="styles_sample_status",
    ),
    path(
        "administration/tenant/styles/sample/<uuid:sample_id>/download/",
        styles_views.sample_download,
        name="styles_sample_download",
    ),
    path(
        "document-styles/<str:digest_asked>.css",
        styles_views.served_view,
        name="organisation_stylesheet",
    ),
]
