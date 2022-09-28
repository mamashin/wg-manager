# -*- coding: utf-8 -*-

__author__ = 'Nikolay Mamashin (mamashin@gmail.com)'

from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.http import HttpResponse
from django.urls import path, include, re_path
from django.conf.urls.static import static
from django.conf import settings

from vpn.views import get_vpn_config


def empty_response(request):
    return HttpResponse('<code>Hello, world via VPN !</code>', status=200)


urlpatterns = [
    path('admin/', admin.site.urls),
    path('cfg/<slug:rnd_id>/', get_vpn_config),
    re_path('.*', empty_response)
]
