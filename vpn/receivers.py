# -*- coding: utf-8 -*-

__author__ = 'Nikolai Mamashin (mamashin@gmail.com)'

from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from loguru import logger
from .models import Server, Client


@receiver(post_save, sender=Server)
def server_post_save(sender, instance: Server, created, **kwargs):
    if created:
        from .services import ssh_keygen
        ssh_keygen(instance.id)


@receiver(post_save, sender=Client)
def client_post_save(sender, instance: Client, created, **kwargs):
    from vpn.services import ssh_remote_server
    logger.info(instance)
    ssh_remote_server(instance.server, client_instance=instance)


@receiver(post_delete, sender=Client)
def client_post_delete(sender, instance: Client, **kwargs):
    from vpn.services import ssh_remote_server
    instance.is_enable = False
    ssh_remote_server(instance.server, client_instance=instance)
