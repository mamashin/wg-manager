# -*- coding: utf-8 -*-

__author__ = 'Nikolai Mamashin (mamashin@gmail.com)'

from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from loguru import logger
from .models import Server, Client


@receiver(post_save, sender=Server)
def server_post_save(sender, instance: Server, created, **kwargs):
    copy_ssh_key_id = None
    if created:
        if exist_srv := Server.objects.filter(ip=instance.ip).first():
            logger.info(f'Exist server with ip {instance.ip}, make copy ssh key from {exist_srv.name}')
            copy_ssh_key_id = exist_srv.id
        from .services import ssh_keygen
        ssh_keygen(instance.id, copy_ssh_key_id)
    if not instance.is_enable:
        from .services import ssh_remote_server
        ssh_remote_server(instance, stop=True)


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
