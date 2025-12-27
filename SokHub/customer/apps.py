from django.apps import AppConfig


class CustomerConfig(AppConfig):
    name = 'customer'
    
    def ready(self):
        """Import signals when app is ready"""
        import customer.signals
