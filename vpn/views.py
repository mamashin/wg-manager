# -*- coding: utf-8 -*-

__author__ = 'Nikolay Mamashin (mamashin@gmail.com)'

from django.http import HttpResponse
from vpn.models import Client
from vpn.services import get_client_file


def get_vpn_config(request, rnd_id):
    wg = Client.objects.filter(rnd=rnd_id).filter(enable_download=True).first()
    if not wg:
        return HttpResponse('Config not found ¯\_(ツ)_/¯', status=404)
    return get_client_file(wg)
