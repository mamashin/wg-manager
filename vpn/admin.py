# -*- coding: utf-8 -*-

import json
from django.contrib import admin
from django.contrib import messages
from django.http import HttpResponseRedirect
from django.utils.html import format_html
from django import forms
from loguru import logger
from .models import Server, Group, Client
from django.urls import path

from .services import get_client_file


class PrettyJSONEncoder(json.JSONEncoder):
    def __init__(self, *args, indent, sort_keys, **kwargs):
        super().__init__(*args, indent=4, sort_keys=True, **kwargs)


class DataForm(forms.ModelForm):
    data = forms.JSONField(encoder=PrettyJSONEncoder, initial=dict, required=False)


@admin.register(Server)
class ServerAdmin(admin.ModelAdmin):
    list_display = ['name', 'ip']
    readonly_fields = ['ssh_copy_id_help', ]
    actions = ['server_restart', 'server_statistic']
    form = DataForm

    @admin.action(description='Restart server')
    def server_restart(self, request, queryset):
        from vpn.services import ssh_remote_server
        for srv in queryset:
            status = ssh_remote_server(srv, restart=True)
            if not status.get('ok'):
                self.message_user(request, f'Error to restart server {srv} - {status.get("msg")}', messages.ERROR)
            if status.get('ok'):
                self.message_user(request, f'Server {srv} restart OK !', messages.SUCCESS)

    @admin.action(description='Server statistic')
    def server_statistic(self, request, queryset):
        from vpn.services import ssh_remote_server
        for srv in queryset:
            status = ssh_remote_server(srv, statistic=True)
            if not status.get('ok'):
                self.message_user(request, f'Error to get statistic from  {srv} - {status.get("msg")}', messages.ERROR)
            if status.get('ok'):
                self.message_user(request, f'Update server {srv} stat OK !', messages.SUCCESS)


@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
    list_display = ['name', ]


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ['name', 'server', 'is_enable',  'group', 'last_seen', 'traffic', 'config_link']
    readonly_fields = ['rnd', 'created_at', 'update_at']
    list_editable = ['is_enable', ]
    form = DataForm
    # change_list_template = "admin/config_wg.html"

    def config_link(self, obj):
        return format_html(f"<a href='get_config/{obj.id}/'>config-{obj.id}</a> (<a href='/cfg/{obj.rnd}/'>link</a>)")

    def get_urls(self):
        urls = super(ClientAdmin, self).get_urls()
        custom_urls = [
            path('get_config/<int:config_id>/', self.client_config, name='get_client_config'), ]
        return custom_urls + urls

    def client_config(self, request, config_id):
        logger.info(config_id)
        return get_client_file(config_id)
