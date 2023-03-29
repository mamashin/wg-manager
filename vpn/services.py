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
        stdin, stdout, stderr = client.exec_command(f'wg show {srv_instance.data.get("interface")}')
        out = stdout.read().decode('utf-8')
        client.close()
        stat_list = [s.strip() for s in out.split('\n')]
        for index, line in enumerate(stat_list):
            if line.startswith('peer') and stat_list[index+1].startswith('endpoint'):
                peer = re.findall(r'peer:\s(\S+)', line)[0]
                last_seen = re.findall(r'latest handshake:\s(.*)', stat_list[index+3])[0]
                traffic = re.findall(r'transfer:\s(.*)', stat_list[index+4])[0]
                cache.set(peer, {'last_seen': last_seen, 'traffic': traffic}, 300)
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
