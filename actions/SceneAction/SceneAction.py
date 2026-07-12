# Import StreamController modules
from src.backend.PluginManager.ActionBase import ActionBase

# Import python modules
import os
from loguru import logger
import threading
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib

class SceneAction(ActionBase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.devices_map = []
        self.scenes_map = []
        
    def on_ready(self) -> None:
        icon_path = os.path.join(self.plugin_base.PATH, "assets", "scene.png")
        self.set_media(media_path=icon_path, size=0.75)
        self.update_labels()

        # Check Govee API Key configuration
        self.plugin_base.prompt_api_key_if_missing()

    def get_config_rows(self) -> list:
        # Load settings
        settings = self.get_settings() or {}
        
        # 1. Device ComboRow
        self.device_model = Gtk.StringList()
        self.device_selector = Adw.ComboRow(
            model=self.device_model,
            title="Govee Device"
        )
        
        # 2. Device Label EntryRow
        self.device_label_entry = Adw.EntryRow(
            title="Device Label",
            text=settings.get("device_label", "")
        )
        
        # 3. Scene ComboRow
        self.scene_model = Gtk.StringList()
        self.scene_selector = Adw.ComboRow(
            model=self.scene_model,
            title="Select Scene"
        )
        
        # 4. Refresh Devices row & button
        self.refresh_button = Gtk.Button.new_from_icon_name("view-refresh-symbolic")
        self.refresh_button.set_valign(Gtk.Align.CENTER)
        self.refresh_button.set_tooltip_text("Refresh Govee Devices/Scenes")
        
        self.refresh_row = Adw.ActionRow(
            title="Refresh Devices/Scenes",
            subtitle="Force update devices and scenes list"
        )
        self.refresh_row.add_suffix(self.refresh_button)
        
        # Build devices map
        self.devices_map = []
        self.scenes_map = []
        
        # Fetch scenes for current device
        def trigger_scenes_fetch(force_refresh=False):
            s = self.get_settings() or {}
            dev_id = s.get("device_id")
            sku = s.get("device_sku")
            if not dev_id or not sku:
                return
                
            new_model = Gtk.StringList()
            new_model.append("Loading scenes...")
            self.scene_selector.set_model(new_model)
            
            def on_scenes_fetched(scenes):
                self.scenes_map = []
                scene_list_model = Gtk.StringList()
                
                selected_scene_idx = 0
                current_scene_id = s.get("scene_id", "")
                
                if not scenes:
                    scene_list_model.append("No scenes available")
                    self.scenes_map.append(("", None))
                else:
                    for idx, scene in enumerate(scenes):
                        name = scene.get("name", "Unnamed Scene")
                        val = scene.get("value", {}) # dict with paramId, id
                        scene_list_model.append(name)
                        # Store name and value
                        self.scenes_map.append((name, val))
                        
                        # Compare unique scene id
                        if str(val.get("id")) == str(current_scene_id):
                            selected_scene_idx = idx
                            
                self.scene_selector.set_model(scene_list_model)
                if self.scenes_map:
                    self.scene_selector.set_selected(selected_scene_idx)
                    
            self.plugin_base.fetch_scenes_async(dev_id, sku, on_scenes_fetched, force_refresh=force_refresh)

        # Populating function for devices
        def populate_devices(devices):
            self.devices_map = []
            new_model = Gtk.StringList()
            
            selected_idx = 0
            current_device_id = settings.get("device_id", "")
            
            if not devices:
                new_model.append("No devices found (Check API Key)")
                self.devices_map.append(("", "", "No devices"))
            else:
                for idx, dev in enumerate(devices):
                    dev_id = dev.get("device")
                    sku = dev.get("sku")
                    name = dev.get("deviceName", "Unnamed Device")
                    display_text = f"{name} ({sku})"
                    new_model.append(display_text)
                    self.devices_map.append((dev_id, sku, name))
                    
                    if dev_id == current_device_id:
                        selected_idx = idx
                        
            self.device_selector.set_model(new_model)
            if self.devices_map:
                self.device_selector.set_selected(selected_idx)
                # Fetch scenes for this device initially
                trigger_scenes_fetch()

        # Connect events
        def on_device_changed(combo, *args):
            idx = combo.get_selected()
            if 0 <= idx < len(self.devices_map):
                dev_id, sku, name = self.devices_map[idx]
                if dev_id:
                    s = self.get_settings()
                    s["device_id"] = dev_id
                    s["device_sku"] = sku
                    s["device_name"] = name
                    # Update label if it was empty or matched the old device name
                    if not s.get("device_label") or s.get("device_label") == s.get("device_name"):
                        s["device_label"] = name
                        self.device_label_entry.set_text(name)
                    self.set_settings(s)
                    trigger_scenes_fetch()
                    self.update_labels()
                    
        def on_device_label_changed(entry, *args):
            text = entry.get_text().strip()
            s = self.get_settings()
            s["device_label"] = text
            self.set_settings(s)
            self.update_labels()
                    
        def on_scene_changed(combo, *args):
            idx = combo.get_selected()
            if 0 <= idx < len(self.scenes_map):
                name, val = self.scenes_map[idx]
                s = self.get_settings()
                if val:
                    s["scene_name"] = name
                    s["scene_id"] = val.get("id")
                    s["scene_param_id"] = val.get("paramId")
                else:
                    s["scene_name"] = ""
                    s["scene_id"] = None
                    s["scene_param_id"] = None
                self.set_settings(s)
                self.update_labels()
            
        def on_refresh_clicked(button):
            self.refresh_button.set_sensitive(False)
            def on_refresh_done(devices):
                populate_devices(devices)
                trigger_scenes_fetch(force_refresh=True)
                self.refresh_button.set_sensitive(True)
            self.plugin_base.fetch_devices_async(on_refresh_done, force_refresh=True)
            
        self.device_selector.connect("notify::selected-item", on_device_changed)
        self.device_label_entry.connect("notify::text", on_device_label_changed)
        self.scene_selector.connect("notify::selected-item", on_scene_changed)
        self.refresh_button.connect("clicked", on_refresh_clicked)
        
        # Populate initial list using cache or fetch if empty
        if self.plugin_base.devices:
            populate_devices(self.plugin_base.devices)
        else:
            new_model = Gtk.StringList()
            new_model.append("Loading devices...")
            self.device_selector.set_model(new_model)
            self.plugin_base.fetch_devices_async(populate_devices)
            
        return [
            self.device_selector,
            self.device_label_entry,
            self.scene_selector,
            self.refresh_row
        ]
        
    def on_key_down(self) -> None:
        threading.Thread(target=self._execute_action, daemon=True).start()
    
    def on_key_up(self) -> None:
        pass

    def _execute_action(self):
        settings = self.get_settings()
        device_id = settings.get("device_id")
        sku = settings.get("device_sku")
        
        if not device_id or not sku:
            logger.warning("Action triggered but device is not configured.")
            return
            
        client = self.plugin_base.govee_client
        if not client or not client.api_key:
            logger.warning("Action triggered but Govee client is not configured.")
            return

        try:
            scene_id = settings.get("scene_id")
            param_id = settings.get("scene_param_id")
            scene_name = settings.get("scene_name", "Unknown Scene")
            
            if scene_id is None or param_id is None:
                logger.warning("Action triggered but scene is not configured.")
                return
                
            value = {
                "id": int(scene_id),
                "paramId": int(param_id)
            }
            
            logger.info(f"Applying scene '{scene_name}' (value: {value}) to device {device_id} ({sku})")
            client.control_device(device_id, sku, "devices.capabilities.dynamic_scene", "lightScene", value)
                
        except Exception as e:
            logger.error(f"Error executing Govee scene action: {e}")

    def update_labels(self) -> None:
        settings = self.get_settings() or {}
        device_label = settings.get("device_label", settings.get("device_name", ""))
        scene_name = settings.get("scene_name", "")
        self.set_top_label(device_label)
        self.set_bottom_label(scene_name)
