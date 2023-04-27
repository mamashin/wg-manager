# -*- coding: utf-8 -*-
__author__ = 'Nikolay Mamashin (mamashin@gmail.com)'

import ipaddress
import os
import re

from decouple import config  # noqa
from django.http import HttpResponse
from django.core.cache import cache
from loguru import logger
from .models import Client, Server

from datetime import datetime
import humanize


def generate_client_config(client_id: int = None) -> list:
    client_instance = Client.objects.get(id=client_id)
    server_instance = Server.objects.get(id=client_instance.server_id)
    all_clients = []
    interface = f"""
[Interface]
Address = {client_instance.data.get('ip')}/32
PrivateKey = {client_instance.data.get('private_key')}
DNS = 1.1.1.1,8.8.8.8
"""
    peer = f"""
[Peer]
Endpoint = {server_instance.ip}:{server_instance.port}
PublicKey = {server_instance.data.get('public_key')}
AllowedIPs = {server_instance.data.get('route') if server_instance.data.get('route') else '0.0.0.0/0'}

"""
    all_clients.append((interface, peer))
    return all_clients


def generate_server_config(srv_id) -> list:
    server_instance = Server.objects.get(id=srv_id)
    all_cfg = []
    network = ipaddress.IPv4Network(server_instance.network)
    interface = f"""
[Interface]
Address =  {network.network_address + 1}/{network.prefixlen}
PrivateKey = {server_instance.data.get('private_key')}
ListenPort = {server_instance.port}
Table = off
"""
    all_cfg.append(interface)

    for client in Client.objects.filter(is_enable=True, server_id=srv_id):
        peer = f"""
[Peer]
# Name = {client.name}
PublicKey = {client.data.get('public_key')}
AllowedIPs = {client.data.get('ip')}/32{',' + client.data.get('allowed') if client.data.get('allowed') else ''}
PersistentKeepalive = {server_instance.data.get('persistent')}

"""
        all_cfg.append(peer)
    return all_cfg


def get_client_file(client_id: int):
    raw_list = generate_client_config(client_id)
    response = HttpResponse(
        content_type='application/octet-stream',
        headers={'Content-Disposition': f'attachment; filename="vpn-wg-{client_id}.conf"'},
    )
    response.write(raw_list[0][0])
    response.write(raw_list[0][1])
    return response


def write_server_config(srv_id):
    srv_data = generate_server_config(srv_id)
    file = open(config('TMP_SERVER_FILE'), 'wb')
    for srv in srv_data:
        file.write(srv.encode())
    file.close()
    os.chmod(config('TMP_SERVER_FILE'), 0o600)


def ssh_keygen(srv_id, copy_ssh_key_id=None):
    # Generate ssh keys for each server, run only once when server created
    import subprocess
    from django.conf import settings
    if copy_ssh_key_id:
        # If server with same ip/hostname exist, copy ssh keys and exit
        subprocess.run(['cp', f'{settings.BASE_DIR}/config/keys/{copy_ssh_key_id}',
                        f'{settings.BASE_DIR}/config/keys/{srv_id}'], capture_output=False)
        subprocess.run(['cp', f'{settings.BASE_DIR}/config/keys/{copy_ssh_key_id}.pub',
                        f'{settings.BASE_DIR}/config/keys/{srv_id}.pub'], capture_output=False)
        return
    subprocess.check_output(f'ssh-keygen -q -t rsa -m PEM -f {settings.BASE_DIR}/config/keys/{srv_id} -N ""',
                            shell=True)


def ssh_remote_server(srv_instance: Server, client_instance: Client = None,
                      restart: bool = False, statistic: bool = False, stop: bool = False) -> dict:
    result = {'ok': False}
    import paramiko
    from django.conf import settings
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(hostname=srv_instance.ip, username='root', timeout=3,
                       key_filename=f'{settings.BASE_DIR}/config/keys/{srv_instance.id}')
    except Exception as e:
        msg = f"can't connect to server via ssh: {e}"
        logger.error(msg)
        result['msg'] = msg
        return result

    if statistic:
        stats = {}
        stdin, stdout, stderr = client.exec_command('wg show all dump')
        out = stdout.read().decode('utf-8')
        client.close()
        """
        Dumps looks like:
        wg0	8GISFUGGDsg1AzV4co7FU6d6YQUyG3txxxxxxxxxxxx=	jvbsBUsx67JP1Au5Ejcy5dyRUzFbxxxxxxxxxxxx=	41800	off
        wg0	ll1spR1+/PLDFVl0AKwzXT2P7fg+svwrU5dd3mx9nSI=	(none)	(none)	172.16.208.2/32	0	0	0	20
        wg0	ZfHvDtfbF7/UANYN4RWa8mli3hL7tRgm5W1Uef/Sjkk=	(none)	(none)	172.16.208.3/32	0	0	0	20
        wg0	p+pVmawyYA63GQZk5uU9VHC5P4+D6CmDAO/UR9vmwR0=	(none)	111.11.111.195:11122	172.16.208.4/32	1680364116	2581732	31106272	20
        """
        for line in [s.strip() for s in out.split('\n')]:
            if not line:
                continue
            params = line.split('\t')
            if len(params) != 9:
                continue
            stats[params[1]] = {
                'interface': params[0],
                'remote_ip': params[3] if params[3] != '(none)' else None,
                'local_ip': params[4] if params[4] != '(none)' else None,
                'last_handshake': params[5],
                'rx_bytes': params[6],
                'tx_bytes': params[7],
                'last_seen': humanize.naturaltime(datetime.fromtimestamp(int(params[5]))) if int(params[5]) else '-',
                'traffic': f'{humanize.naturalsize(int(params[6]))} / {humanize.naturalsize(int(params[7]))}'
            }
            # Store to cache for 5 minutes
            cache.set(params[1], stats[params[1]], 300)

        result['ok'] = True
        return result

    sftp = client.open_sftp()
    write_server_config(srv_instance.id)

    remote_cfg_path = f'{config("WIREGUARD_CONFIG_BASE_PATH")}/{srv_instance.data.get("interface")}.conf'
    sftp.put(config('TMP_SERVER_FILE'), remote_cfg_path)
    sftp.chmod(remote_cfg_path, 0o600)

    if client_instance and client_instance.is_enable:
        stdin, stdout, stderr = client.exec_command(client_instance.set_add)
    if client_instance and not client_instance.is_enable:
        stdin, stdout, stderr = client.exec_command(client_instance.set_remove)

    if restart:
        stdin, stdout, stderr = client.exec_command(f"service wg-quick@{srv_instance.data.get('interface')} restart")
    if stop:
        stdin, stdout, stderr = client.exec_command(f"service wg-quick@{srv_instance.data.get('interface')} stop")
    sftp.close()
    client.close()

    result['ok'] = True
    return result
