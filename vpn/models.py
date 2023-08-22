# -*- coding: utf-8 -*-
import random
import re
from loguru import logger

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.core.cache import cache
from django.contrib.auth.models import User
from ipaddress import IPv4Network, ip_address, AddressValueError, ip_network
from django.utils.translation import gettext_lazy as _


def default_server_data():
    return {'interface': 'wg0'}


class Server(models.Model):
    name = models.CharField(max_length=255, blank=False, null=False, verbose_name=_("Server name"))
    ip = models.CharField(max_length=255, verbose_name="IP/Hostname", default='0.0.0.0', blank=False, null=False)
    port = models.IntegerField(verbose_name="port", default=41800, blank=False)
    network = models.CharField(max_length=255, verbose_name="Network", default='10.10.10.0/24', blank=False, null=False)
    data = models.JSONField(default=default_server_data, verbose_name="Server data", blank=True)
    is_enable = models.BooleanField(default=True, verbose_name=_("Active"))

    def __str__(self):
        return f'{self.name}'

    class Meta:
        verbose_name = _('Server')
        verbose_name_plural = _('Servers')

    @property
    def ssh_copy_id_help(self) -> str:
        if self.name:
            return f'ssh-copy-id -i {settings.BASE_DIR}/config/keys/{self.id}.pub root@{self.ip}'
        return "-"

    def clean(self):
        try:
            IPv4Network(self.network)
        except (ValueError, AddressValueError):
            raise ValidationError({"network": "Not looks like valid network"})

    def save(self, *args, **kwargs):
        created = self._state.adding
        if created:
            private_key, public_key = key_gen()
            self.data['interface'] = 'wg0'
            self.data['persistent'] = 20
            self.data['route'] = '0.0.0.0/0'
            self.data['private_key'] = private_key
            self.data['public_key'] = public_key
        super(Server, self).save(*args, **kwargs)


class Group(models.Model):
    name = models.CharField(max_length=255, blank=False, null=False, verbose_name="Client group")
    ips = models.TextField(verbose_name=_("Allowed IPs"), blank=True, null=True, default='0.0.0.0/0')
    description = models.CharField(verbose_name=_("Description"), blank=True, null=True, max_length=255)

    def __str__(self):
        return f'{self.name}'

    class Meta:
        verbose_name = _('Client group')
        verbose_name_plural = _('Client groups')

    def clean(self):
        clean_string = re.sub(r'\s+', '', self.ips)
        if '0.0.0.0/0' in clean_string:
            self.ips = '0.0.0.0/0'
            return

        clean_string_list = clean_string.strip(',').split(',')
        for ip in clean_string_list:
            try:
                ip_network(ip, strict=False)
            except (ValueError, AddressValueError):
                raise ValidationError({"ips": f"{ip} - not looks like valid IP address or network"})
        self.ips = ',\n'.join(clean_string_list)

    @property
    def ips_for_config(self):
        clean_string = re.sub(r'\s+', '', self.ips)
        return clean_string


class Client(models.Model):
    name = models.CharField(max_length=255, verbose_name=_("Client name"), db_index=True, blank=False, null=False)
    description = models.TextField(verbose_name=_("Description"), blank=True, null=True)
    is_enable = models.BooleanField(default=True, verbose_name=_("Active"))
    created_at = models.DateTimeField(verbose_name=_("Create time"), auto_now_add=True)
    update_at = models.DateTimeField(verbose_name=_("Update time"), auto_now=True)
    group = models.ForeignKey(Group, null=False, on_delete=models.DO_NOTHING, verbose_name=_("Client group"))
    rnd = models.CharField(max_length=255, blank=True, null=True, verbose_name="RND ID", db_index=True)
    server = models.ForeignKey(Server, blank=False, null=True,
                               on_delete=models.SET_NULL, verbose_name=_('Server'))
    data = models.JSONField(default=dict, verbose_name=_("Client data"), blank=True)
    download_count = models.IntegerField(default=0, verbose_name=_("Download count"))
    enable_download = models.BooleanField(default=True, verbose_name=_("Enable download"))

    def __str__(self):
        return f'{self.name}'

    class Meta:
        verbose_name = _('Client')
        verbose_name_plural = _('Clients')

    @property
    def set_add(self) -> str:
        interface = self.server.data.get('interface') if self.server.data.get('interface') else 'wg0'
        return f'wg set {interface} peer {self.data.get("public_key")} allowed-ips {self.data.get("ip")}/32' \
               f'{"," + self.data.get("allowed") if self.data.get("allowed") else ""} '\
               f'persistent-keepalive {self.server.data.get("persistent")}'

    @property
    def set_remove(self) -> str:
        interface = self.server.data.get('interface') if self.server.data.get('interface') else 'wg0'
        return f'wg set {interface} peer {self.data.get("public_key")} remove'

    @property
    def last_seen(self) -> str:
        cache_data = cache.get(self.data.get('public_key'))
        if cache_data:
            return cache_data.get('last_seen')
        return '-'

    @property
    def traffic(self) -> str:
        cache_data = cache.get(self.data.get('public_key'))
        if cache_data:
            return cache_data.get('traffic')
        return '-'

    @property
    def remote_ip(self) -> str:
        cache_data = cache.get(self.data.get('public_key'))
        if cache_data and cache_data.get('remote_ip'):
            return cache_data.get('remote_ip').split(':')[0]
        return '-'

    def save(self, *args, **kwargs):
        created = self._state.adding
        if created:
            private_key, public_key = key_gen()
            server_instance = Server.objects.get(id=self.server_id)
            network = IPv4Network(server_instance.network)
            last_ip = server_instance.data.get('last_ip')
            if not last_ip:
                last_ip = int(network.network_address) + 1

            last_ip = ip_address(int(ip_address(last_ip)) + 1)
            server_instance.data['last_ip'] = str(last_ip)
            server_instance.save()

            self.data['ip'] = str(last_ip)
            self.data['private_key'] = private_key
            self.data['public_key'] = public_key
            self.rnd = f'%0{6}x' % random.randrange(16**6)

        super(Client, self).save(*args, **kwargs)


def key_gen() -> list:
    from .keygen import PrivateKey
    private_key = PrivateKey.generate()
    public_key = private_key.public_key()

    return [str(private_key), str(public_key)]
