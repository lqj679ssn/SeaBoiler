from django.urls import path

from User.api_views import CodeView, UserView

urlpatterns = [
    path('code', CodeView.as_view()),
    path('', UserView.as_view()),
]