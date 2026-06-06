from django.apps import AppConfig


class ConsultantsConfig(AppConfig):
    name = 'consultants'

    def ready(self):
        import consultants.signals

