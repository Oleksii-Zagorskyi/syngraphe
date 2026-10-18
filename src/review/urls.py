from django.urls import path

from review.views import accept, history, pending, return_run, revert, undo

urlpatterns = [
    path("document/<int:number>/pending/", pending.page, name="document_pending"),
    path("document/<int:number>/pending/accept/", accept.accept, name="document_accept"),
    path("document/<int:number>/pending/return/", return_run.return_run, name="document_return"),
    path("document/<int:number>/history/", history.page, name="document_history"),
    path("document/<int:number>/history/undo/", undo.undo_view, name="document_undo"),
    path("document/<int:number>/pending/revert/", revert.revert_view, name="document_revert"),
]
