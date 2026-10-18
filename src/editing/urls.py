from django.urls import path

from editing.views import (
    appendix,
    capture,
    draft,
    edit_tab,
    entities,
    finish,
    images,
    parts,
    reservations,
    title_page,
)

urlpatterns = [
    path("document/<int:number>/edit/", edit_tab.page, name="document_edit"),
    path("document/<int:number>/edit/take/", edit_tab.take, name="document_edit_take"),
    path("document/<int:number>/edit/load/", draft.load, name="document_edit_load"),
    path("document/<int:number>/edit/capture/", capture.capture, name="document_edit_capture"),
    path(
        "document/<int:number>/edit/heartbeat/", capture.heartbeat, name="document_edit_heartbeat"
    ),
    path("document/<int:number>/edit/close/", capture.close, name="document_edit_close"),
    path("document/<int:number>/edit/changes/", capture.changes, name="document_edit_changes"),
    path("document/<int:number>/edit/finish/", finish.finish, name="document_edit_finish"),
    path(
        "document/<int:number>/edit/title-page/",
        title_page.switch,
        name="document_edit_title_page",
    ),
    path("document/<int:number>/edit/send/", finish.send, name="document_edit_send"),
    path("document/<int:number>/edit/discard/", finish.discard, name="document_edit_discard"),
    path("document/<int:number>/my-edits/", finish.my_edits, name="document_my_edits"),
    path("document/<int:number>/edit/reserve/", reservations.reserve, name="document_edit_reserve"),
    path(
        "document/<int:number>/edit/cancel-reservation/",
        reservations.cancel,
        name="document_edit_cancel_reservation",
    ),
    path("my-reservations/", reservations.my_reservations, name="my_reservations"),
    path(
        "document/<int:number>/edit/end-reservation/",
        reservations.end,
        name="document_edit_end_reservation",
    ),
    path(
        "document/<int:number>/edit/take-back/",
        reservations.take_back,
        name="document_edit_take_back",
    ),
    path(
        "document/<int:number>/edit/discard-draft/",
        reservations.discard_draft,
        name="document_edit_discard_draft",
    ),
    path(
        "document/<int:number>/edit/force-release/",
        reservations.force,
        name="document_edit_force_release",
    ),
    path(
        "administration/tenant/reservations/",
        reservations.administration,
        name="reservations",
    ),
    path(
        "document/<int:number>/edit/image/",
        images.upload,
        name="document_edit_image_upload",
    ),
    path(
        "document/<int:number>/edit/image/<str:name>/",
        images.draft_image,
        name="document_edit_image",
    ),
    path(
        "document/<int:number>/edit/entities/",
        entities.declare,
        name="document_edit_entities",
    ),
    path(
        "document/<int:number>/appendix/<int:part>/edit/",
        appendix.page,
        name="document_appendix_edit",
    ),
    path(
        "document/<int:number>/appendix/<int:part>/edit/load/",
        appendix.load,
        name="document_appendix_edit_load",
    ),
    path(
        "document/<int:number>/edit/parts/appendix/",
        parts.create_appendix,
        name="document_parts_appendix_create",
    ),
    path(
        "document/<int:number>/edit/parts/appendix/<int:part>/rename/",
        parts.rename_appendix,
        name="document_parts_appendix_rename",
    ),
    path(
        "document/<int:number>/edit/parts/appendix/<int:part>/delete/",
        parts.delete_appendix,
        name="document_parts_appendix_delete",
    ),
    path(
        "document/<int:number>/edit/parts/appendices/order/",
        parts.reorder_appendices,
        name="document_parts_appendices_order",
    ),
    path(
        "document/<int:number>/edit/parts/attachment/",
        parts.upload_attachment,
        name="document_parts_attachment_upload",
    ),
    path(
        "document/<int:number>/edit/parts/attachment/<int:part>/",
        parts.attachment,
        name="document_parts_attachment",
    ),
    path(
        "document/<int:number>/edit/parts/attachment/<int:part>/replace/",
        parts.replace_attachment,
        name="document_parts_attachment_replace",
    ),
    path(
        "document/<int:number>/edit/parts/attachment/<int:part>/rename/",
        parts.rename_attachment,
        name="document_parts_attachment_rename",
    ),
    path(
        "document/<int:number>/edit/parts/attachment/<int:part>/delete/",
        parts.delete_attachment,
        name="document_parts_attachment_delete",
    ),
    path(
        "document/<int:number>/edit/parts/attachments/order/",
        parts.reorder_attachments,
        name="document_parts_attachments_order",
    ),
]
