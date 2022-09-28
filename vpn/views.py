# -*- coding: utf-8 -*-

__author__ = 'Nikolay Mamashin (mamashin@gmail.com)'

from django.http import HttpResponse
from vpn.models import Client
from vpn.services import get_client_file


def get_vpn_config(request, rnd_id):
    wg = Client.objects.filter(rnd=rnd_id).first()
    if not wg:
        return HttpResponse('Config not found', status=404)
    return get_client_file(wg.id)
