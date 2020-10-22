import django.dispatch

trigger_materialization = django.dispatch.Signal(providing_args=["sender", "instance", "algorithm"])
