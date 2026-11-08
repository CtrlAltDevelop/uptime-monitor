from django.contrib import admin
from django.urls import path

from monitor.api import api
from monitor.views import dashboard

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", api.urls),
    path("", dashboard, name="dashboard"),
]
