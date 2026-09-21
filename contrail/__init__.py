def classFactory(iface):
    """Entry point required by QGIS to load the plugin."""
    from .contrail_plugin import ContrailPlugin
    return ContrailPlugin(iface)
