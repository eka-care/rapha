from django.apps import AppConfig

PLUGIN_NAME = "care_phc"


class PhcConfig(AppConfig):
    name = PLUGIN_NAME
    verbose_name = "Primary health centre workflow"

    def ready(self):
        from care_phc.permissions import register

        register()
