# Import StreamController modules
from src.backend.PluginManager.PluginBase import PluginBase
from src.backend.PluginManager.ActionHolder import ActionHolder

# Import python & gtk modules
import os
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib

# Import actions
from .actions.SimpleAction.SimpleAction import SimpleAction

class PluginTemplate(PluginBase):
    def __init__(self):
        super().__init__()

        ## Register actions
        self.simple_action_holder = ActionHolder(
            plugin_base = self,
            action_base = SimpleAction,
            action_id = "com_oparada_GoveeStreamController::SimpleAction",
            action_name = "Simple Action",
        )
        self.add_action_holder(self.simple_action_holder)

        # Register plugin
        self.register(
            plugin_name = "Govee Streamcontroller",
            github_repo = "https://github.com/oparada1988/Govee-Streamcontroller",
            plugin_version = "1.0.0",
            app_version = "1.1.1-alpha"
        )

    def get_settings_area(self):
        group = Adw.PreferencesGroup(title="Govee Plugin Settings")
        
        # API Key row
        api_key_row = Adw.EntryRow(title="Govee API Key")
        
        # Load current setting
        settings = self.get_settings()
        api_key_row.set_text(settings.get("api_key", ""))
        
        # Connect changes to save setting
        def on_api_key_changed(entry, *args):
            s = self.get_settings()
            s["api_key"] = entry.get_text().strip()
            self.set_settings(s)
            
        api_key_row.connect("notify::text", on_api_key_changed)
        group.add(api_key_row)
        
        return group