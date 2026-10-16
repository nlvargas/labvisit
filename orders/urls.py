from django.urls import path

from . import views

urlpatterns = [
    path("", views.start, name="start"),
    path("order/manual/", views.start_manual, name="start_manual"),
    path("order/<uuid:public_id>/", views.order_detail, name="order"),
    path("order/<uuid:public_id>/details/", views.order_details, name="order_details"),
    path("order/<uuid:public_id>/retry/", views.retry_order, name="retry_order"),
    path("order/<uuid:public_id>/status/", views.order_status, name="order_status"),
    path("order/<uuid:public_id>/lines/<int:line_id>/toggle/", views.toggle_line, name="toggle_line"),
    path("order/<uuid:public_id>/lines/<int:line_id>/choose/<int:exam_id>/", views.choose_line, name="choose_line"),
    path("order/<uuid:public_id>/search/", views.search_exams, name="search_exams"),
    path("order/<uuid:public_id>/add/<int:exam_id>/", views.add_exam, name="add_exam"),
    path("order/<uuid:public_id>/exams/", views.exams, name="exams"),
    path("order/<uuid:public_id>/schedule/", views.schedule, name="schedule"),
    path("order/<uuid:public_id>/book/", views.book, name="book"),
    path("order/<uuid:public_id>/calendar.ics", views.calendar_event, name="calendar_event"),
]
