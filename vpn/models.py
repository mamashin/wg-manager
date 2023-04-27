# -*- coding: utf-8 -*-
import random

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.core.cache import cache
from django.contrib.auth.models import User
from ipaddress import IPv4Network, ip_address, AddressValueError


def default_server_data():
    return {'interface': 'wg0'}


class Server(models.Model):
    name = models.CharField(max_length=255, blank=False, null=False, verbose_name="Server name")
    ip = models.CharField(max_length=255, verbose_name="IP/Hostname", default='0.0.0.0', blank=False, null=False)
    port = models.IntegerField(verbose_name="port", default=41800, blank=False)
    network = models.CharField(max_length=255, verbose_name="Network", default='10.10.10.0/24', blank=False, null=False)
    data = models.JSONField(default=default_server_data, verbose_name="Server data", blank=True)
    is_enable = models.BooleanField(default=True, verbose_name="Active")

    def __str__(self):
        return f'{self.name}'

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

    def __str__(self):
        return f'{self.name}'


class Client(models.Model):
    name = models.CharField(max_length=255, verbose_name="Client name", db_index=True, blank=False, null=False)
    is_enable = models.BooleanField(default=True, verbose_name="Active")
    created_at = models.DateTimeField(verbose_name="Create time", auto_now_add=True)
    update_at = models.DateTimeField(verbose_name="Update time", auto_now=True)
    group = models.ForeignKey(Group, null=False, on_delete=models.DO_NOTHING)
    rnd = models.CharField(max_length=255, blank=True, null=True, verbose_name="RND ID", db_index=True)
    server = models.ForeignKey(Server, blank=False, null=True,
                               on_delete=models.SET_NULL, verbose_name='Server')
    data = models.JSONField(default=dict, verbose_name="Client data", blank=True)

    def __str__(self):
        return f'{self.name}'

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
