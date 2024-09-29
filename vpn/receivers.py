# -*- coding: utf-8 -*-

__author__ = 'Nikolai Mamashin (mamashin@gmail.com)'

import subprocess
import time

from django.db.models.signals import post_save, post_delete, pre_delete
from django.dispatch import receiver
from loguru import logger

from config import settings
from .models import Server, Client


@receiver(post_save, sender=Server)
def server_post_save(sender, instance: Server, created, **kwargs):
    copy_ssh_key_id = None
    if created:
        from .services import ssh_keygen, ssh_remote_server

        if exist_srv := Server.objects.filter(ip=instance.ip).exclude(pk=instance.id).first():
            logger.info(f'Exist server with ip {instance.ip}, make copy ssh key from {exist_srv.name}')
            copy_ssh_key_id = exist_srv.id
        ssh_keygen(instance.id, copy_ssh_key_id)
        time.sleep(1)
        # TODO: When new (!) server created, we need copy ssh key to server (manually), before we can ssh to server
        ssh_remote_server(instance, cmd='firewall_add')

    if not instance.is_enable:
        from .services import ssh_remote_server
        ssh_remote_server(instance, cmd='stop')


@receiver(pre_delete, sender=Server)
def server_pre_delete(sender, instance: Server, **kwargs):
    from .services import ssh_remote_server
    # Clean up
    ssh_remote_server(instance, cmd='stop')
    ssh_remote_server(instance, cmd='disable')
    ssh_remote_server(instance, cmd='firewall_remove')
    ssh_remote_server(instance, cmd='config_remove')
    try:
        subprocess.run(['rm', f'{settings.BASE_DIR}/config/keys/{instance.id}.pub'], capture_output=False)
        subprocess.run(['rm', f'{settings.BASE_DIR}/config/keys/{instance.id}'], capture_output=False)
    except Exception as e:
        logger.error(f'Error delete ssh keys - {e}')


@receiver(post_save, sender=Client)
def client_post_save(sender, instance: Client, created, **kwargs):
    from vpn.services import ssh_remote_server
    # logger.info(instance)
    ssh_remote_server(instance.server, client_instance=instance)


@receiver(post_delete, sender=Client)
def client_post_delete(sender, instance: Client, **kwargs):
    from vpn.services import ssh_remote_server
    instance.is_enable = False
    ssh_remote_server(instance.server, client_instance=instance)
