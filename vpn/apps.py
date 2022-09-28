from django.apps import AppConfig
from django.utils.module_loading import autodiscover_modules


class VpnConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'vpn'

    def ready(self):
        # Automatically import all receivers files
        autodiscover_modules('receivers')
