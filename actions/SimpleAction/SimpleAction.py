# Import StreamController modules
from src.backend.PluginManager.ActionBase import ActionBase
from src.backend.DeckManagement.DeckController import DeckController
from src.backend.PageManagement.Page import Page
from src.backend.PluginManager.PluginBase import PluginBase

# Import python modules
import os

# Import gtk modules - used for the config rows
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib

class SimpleAction(ActionBase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
    def on_ready(self) -> None:
        icon_path = os.path.join(self.plugin_base.PATH, "assets", "info.png")
        self.set_media(media_path=icon_path, size=0.75)
        
        # Check Govee API Key configuration
        plugin_settings = self.plugin_base.get_settings()
        api_key = plugin_settings.get("api_key", "")
        
        action_settings = self.get_settings()
        warning_shown = action_settings.get("warning_shown", False)
        
        if not api_key and not warning_shown:
            action_settings["warning_shown"] = True
            self.set_settings(action_settings)
            
            def show_dialog():
                dialog = Gtk.MessageDialog(
                    transient_for=None,
                    modal=True,
                    message_type=Gtk.MessageType.WARNING,
                    buttons=Gtk.ButtonsType.OK,
                    text="Govee API Key Required",
                )
                dialog.set_secondary_text(
                    "Please configure your Govee API Key in the plugin's global settings to use Govee actions."
                )
                dialog.connect("response", lambda d, r: d.destroy())
                dialog.show()
                return False
                
            GLib.idle_add(show_dialog)
        
    def on_key_down(self) -> None:
        print("Key down")
    
    def on_key_up(self) -> None:
        print("Key up")