# Import StreamController modules
from src.backend.PluginManager.PluginBase import PluginBase
from src.backend.PluginManager.ActionHolder import ActionHolder

# Import python & gtk modules
import os
import gi
import logging
import threading
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib

# Import actions
from .actions.SimpleAction.SimpleAction import SimpleAction
from .actions.BrightnessAction.BrightnessAction import BrightnessAction
from .actions.SceneColorAction.SceneColorAction import SceneColorAction
from .govee_api import GoveeAPIClient

logger = logging.getLogger("GoveeStreamController.Plugin")

class PluginTemplate(PluginBase):
    def __init__(self):
        super().__init__()

        ## Initialize cache & coalescing lists
        self.devices = []
        self.devices_loading = False
        self.devices_callbacks = []
        
        self.scenes_cache = {}
        self.scenes_callbacks = {}
        self.scenes_loading = set()
        
        self.api_key_prompt_active = False

        ## Initialize Govee API Client
        settings = self.get_settings()
        self.govee_client = GoveeAPIClient(settings.get("api_key", ""))

        ## Register actions
        self.simple_action_holder = ActionHolder(
            plugin_base = self,
            action_base = SimpleAction,
            action_id = "com_oparada_GoveeStreamController::SimpleAction",
            action_name = "Power Toggle",
        )
        self.add_action_holder(self.simple_action_holder)

        self.brightness_action_holder = ActionHolder(
            plugin_base = self,
            action_base = BrightnessAction,
            action_id = "com_oparada_GoveeStreamController::BrightnessAction",
            action_name = "Brightness Control",
        )
        self.add_action_holder(self.brightness_action_holder)

        self.scenecolor_action_holder = ActionHolder(
            plugin_base = self,
            action_base = SceneColorAction,
            action_id = "com_oparada_GoveeStreamController::SceneColorAction",
            action_name = "Scene & Color",
        )
        self.add_action_holder(self.scenecolor_action_holder)

        # Register plugin
        self.register(
            plugin_name = "Govee Streamcontroller",
            github_repo = "https://github.com/oparada1988/Govee-Streamcontroller",
            plugin_version = "1.0.0",
            app_version = "1.1.1-alpha"
        )

    def fetch_devices_async(self, callback=None, force_refresh: bool = False):
        if not force_refresh and self.devices:
            if callback:
                callback(self.devices)
            return

        if callback:
            self.devices_callbacks.append(callback)

        if self.devices_loading:
            return

        self.devices_loading = True
        
        def run_fetch():
            try:
                logger.info("Fetching Govee devices from API...")
                devices = self.govee_client.get_devices()
                self.devices = devices
            except Exception as e:
                logger.error(f"Error fetching Govee devices: {e}")
            finally:
                self.devices_loading = False
                callbacks_to_run = list(self.devices_callbacks)
                self.devices_callbacks.clear()
                for cb in callbacks_to_run:
                    GLib.idle_add(cb, self.devices)

        threading.Thread(target=run_fetch, daemon=True).start()

    def fetch_scenes_async(self, device: str, sku: str, callback=None, force_refresh: bool = False):
        if not force_refresh and device in self.scenes_cache:
            if callback:
                callback(self.scenes_cache[device])
            return

        if callback:
            if device not in self.scenes_callbacks:
                self.scenes_callbacks[device] = []
            self.scenes_callbacks[device].append(callback)

        if device in self.scenes_loading:
            return

        self.scenes_loading.add(device)

        def run_fetch():
            try:
                logger.info(f"Fetching scenes for {device} ({sku})...")
                scenes = self.govee_client.get_scenes(device, sku)
                if scenes:
                    self.scenes_cache[device] = scenes
            except Exception as e:
                logger.error(f"Error fetching Govee scenes: {e}")
                scenes = []
            finally:
                self.scenes_loading.discard(device)
                callbacks_to_run = self.scenes_callbacks.pop(device, [])
                for cb in callbacks_to_run:
                    GLib.idle_add(cb, scenes)

        threading.Thread(target=run_fetch, daemon=True).start()

    def prompt_api_key_if_missing(self):
        settings = self.get_settings()
        api_key = settings.get("api_key", "")
        if api_key or getattr(self, "api_key_prompt_active", False):
            return

        self.api_key_prompt_active = True

        def show_prompt():
            dialog = Gtk.MessageDialog(
                transient_for=None,
                modal=True,
                message_type=Gtk.MessageType.QUESTION,
                buttons=Gtk.ButtonsType.OK_CANCEL,
                text="Govee API Key Required",
            )
            dialog.set_secondary_text(
                "Please enter your Govee Developer API Key to configure Govee actions directly:"
            )
            
            content_area = dialog.get_content_area()
            
            # Create Gtk.Entry for inputting the API key
            entry = Gtk.Entry()
            entry.set_placeholder_text("Govee API Key")
            entry.set_margin_top(12)
            entry.set_margin_bottom(12)
            entry.set_visibility(True)
            content_area.append(entry)
            
            def on_response(d, response_id):
                self.api_key_prompt_active = False
                if response_id == Gtk.ResponseType.OK:
                    new_key = entry.get_text().strip()
                    if new_key:
                        s = self.get_settings()
                        s["api_key"] = new_key
                        self.set_settings(s)
                        self.govee_client.api_key = new_key
                        # Force refresh devices list automatically on key input
                        self.fetch_devices_async(force_refresh=True)
                d.destroy()
                
            dialog.connect("response", on_response)
            dialog.present()
            return False
            
        GLib.idle_add(show_prompt)

    def get_settings_area(self):
        group = Adw.PreferencesGroup(title="Govee Plugin Settings")
        
        # API Key row
        api_key_row = Adw.EntryRow(title="Govee API Key")
        
        # Load current setting
        settings = self.get_settings()
        api_key_row.set_text(settings.get("api_key", ""))
        
        # Connect changes to save setting and update Govee Client
        def on_api_key_changed(entry, *args):
            s = self.get_settings()
            api_key = entry.get_text().strip()
            s["api_key"] = api_key
            self.set_settings(s)
            self.govee_client.api_key = api_key
            # Clear caches upon key change to prevent displaying stale information
            self.devices = []
            self.scenes_cache = {}
            
        api_key_row.connect("notify::text", on_api_key_changed)
        group.add(api_key_row)
        
        return group