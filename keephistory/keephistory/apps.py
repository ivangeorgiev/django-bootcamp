from django.apps import AppConfig

class MyAppConfig(AppConfig):
    name = 'keephistory'

    def ready(self):
        from . import signals
