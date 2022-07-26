from django.urls import re_path

from .views import LoginView, CallbackView, LogoutView


urlpatterns = [
    re_path(r'^oauth2/login/?$', LoginView.as_view(), name='oauth2_login_view'),
    re_path(r'^oauth2/callback/?$', CallbackView.as_view(), name='oauth2_callback_view'),
    re_path(r'^oauth2/logout/?$', LogoutView.as_view(), name='oauth2_logout_view'),
]
