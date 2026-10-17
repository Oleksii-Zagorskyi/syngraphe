from django.urls import include, path

from documents import administration, corpus_views, image_views, views

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
    # Epic 10
    path("search/", corpus_views.search, name="search"),
    path("document/<int:number>/archive/", corpus_views.archive, name="document_archive"),
    path("document/<int:number>/restore/", corpus_views.restore, name="document_restore"),
    path("document/<int:number>/copy/", corpus_views.copy, name="document_copy"),
    path("administration/tenant/archive/", administration.archived, name="archive"),
    path("administration/tenant/folders/", administration.folders, name="folders"),
    path("administration/tenant/folders/new/", administration.folder_new, name="folder_new"),
    path(
        "administration/tenant/folders/<int:number>/rename/",
        administration.folder_rename,
        name="folder_rename",
    ),
    path(
        "administration/tenant/folders/<int:number>/delete/",
        administration.folder_delete,
        name="folder_delete",
    ),
    path(
        "administration/tenant/folders/<int:number>/move/",
        administration.folder_move,
        name="folder_move",
    ),
    path(
        "administration/tenant/document-types/",
        administration.document_types,
        name="document_types",
    ),
    path(
        "document/<int:number>/info/type/",
        corpus_views.change_type,
        name="document_type_change",
    ),
    path("", include("editing.urls")),
    path("", include("review.urls")),
    path("", include("editions.urls")),
    path("", include("rendering.urls")),
    path("document/<int:number>/image/<str:name>/", image_views.image, name="document_image"),
]
