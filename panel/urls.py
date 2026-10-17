from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

urlpatterns = [
    path("", views.agenda, name="panel_agenda"),
    path("login/", auth_views.LoginView.as_view(template_name="panel/login.html"), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("route/<str:day>/", views.route, name="panel_route"),
    path("order/<uuid:public_id>/", views.order_detail, name="panel_order"),
    path("order/<uuid:public_id>/file/", views.order_file, name="panel_order_file"),
    path("order/<uuid:public_id>/<slug:action>/", views.order_action, name="panel_order_action"),
]
