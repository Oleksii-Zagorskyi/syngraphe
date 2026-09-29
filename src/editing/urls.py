from django.urls import path

from editing.views import capture, draft, edit_tab, finish

urlpatterns = [
    path("document/<int:number>/edit/", edit_tab.page, name="document_edit"),
    path("document/<int:number>/edit/take/", edit_tab.take, name="document_edit_take"),
    path("document/<int:number>/edit/load/", draft.load, name="document_edit_load"),
    path("document/<int:number>/edit/capture/", capture.capture, name="document_edit_capture"),
    path(
        "document/<int:number>/edit/heartbeat/", capture.heartbeat, name="document_edit_heartbeat"
    ),
    path("document/<int:number>/edit/close/", capture.close, name="document_edit_close"),
    path("document/<int:number>/edit/finish/", finish.finish, name="document_edit_finish"),
    path("document/<int:number>/edit/send/", finish.send, name="document_edit_send"),
    path("document/<int:number>/my-edits/", finish.my_edits, name="document_my_edits"),
]
