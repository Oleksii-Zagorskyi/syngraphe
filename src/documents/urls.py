from django.urls import include, path

from documents import views

urlpatterns = [
    path("document/new/", views.create, name="document_create"),
    path("folder/<int:number>/", views.folder, name="folder"),
    path("in-review/", views.in_review, name="in_review"),
    path("in-edit/", views.in_edit, name="in_edit"),
    path("document/<int:number>/", views.page, name="document"),
    path("document/<int:number>/info/", views.page, {"tab": "info"}, name="document_info"),
    path(
        "document/<int:number>/attachment/<int:part>/",
        views.attachment,
        name="document_attachment",
    ),
    path("", include("editing.urls")),
    path("", include("review.urls")),
    path("", include("editions.urls")),
    path("", include("rendering.urls")),
]
