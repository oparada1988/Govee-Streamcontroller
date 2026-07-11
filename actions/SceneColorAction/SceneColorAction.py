# Import StreamController modules
from src.backend.PluginManager.ActionBase import ActionBase
from src.backend.DeckManagement.InputIdentifier import Input, InputEvent

# Import python modules
import os
from loguru import logger
import threading
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib, Gdk

class SceneColorAction(ActionBase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.devices_map = []
        self.scenes_map = []
        
    def on_ready(self) -> None:
        icon_path = os.path.join(self.plugin_base.PATH, "assets", "info.png")
        self.set_media(media_path=icon_path, size=0.75)

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
        
        # 2. Mode ComboRow (Color vs Scene)
        self.mode_model = Gtk.StringList()
        self.mode_model.append("Set Color")
        self.mode_model.append("Apply Scene")
        self.mode_selector = Adw.ComboRow(
            model=self.mode_model,
            title="Action Mode"
        )
        current_mode = settings.get("mode", "color")
        self.mode_selector.set_selected(0 if current_mode == "color" else 1)
        
        # 3. Color Picker Button inside an ActionRow
        self.color_button = Gtk.ColorButton()
        self.color_button.set_valign(Gtk.Align.CENTER)
        
        # Parse initial color
        current_color = settings.get("color_hex", "#FFFFFF")
        rgba = Gdk.RGBA()
        rgba.parse(current_color)
        self.color_button.set_rgba(rgba)
        
        self.color_row = Adw.ActionRow(
            title="Set Color",
            subtitle="Click the color block to pick a color"
        )
        self.color_row.add_suffix(self.color_button)
        
        # 4. Scene ComboRow
        self.scene_model = Gtk.StringList()
        self.scene_selector = Adw.ComboRow(
            model=self.scene_model,
            title="Select Scene"
        )
        
        # 5. Refresh Devices row & button
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
                    self.set_settings(s)
                    trigger_scenes_fetch()
                    
        def on_mode_changed(combo, *args):
            idx = combo.get_selected()
            mode = "color" if idx == 0 else "scene"
            s = self.get_settings()
            s["mode"] = mode
            self.set_settings(s)
            update_visibility()
            if mode == "scene" and not self.scenes_map:
                trigger_scenes_fetch()
                    
        def on_color_set(button):
            rgba = button.get_rgba()
            r = int(rgba.red * 255)
            g = int(rgba.green * 255)
            b = int(rgba.blue * 255)
            hex_color = f"#{r:02X}{g:02X}{b:02X}"
            s = self.get_settings()
            s["color_hex"] = hex_color
            self.set_settings(s)

        def on_scene_changed(combo, *args):
            idx = combo.get_selected()
            if 0 <= idx < len(self.scenes_map):
                name, val = self.scenes_map[idx]
                if val:
                    s = self.get_settings()
                    s["scene_name"] = name
                    s["scene_id"] = val.get("id")
                    s["scene_param_id"] = val.get("paramId")
                    self.set_settings(s)
            
        def on_refresh_clicked(button):
            self.refresh_button.set_sensitive(False)
            def on_refresh_done(devices):
                populate_devices(devices)
                trigger_scenes_fetch(force_refresh=True)
                self.refresh_button.set_sensitive(True)
            self.plugin_base.fetch_devices_async(on_refresh_done, force_refresh=True)

        def update_visibility():
            s = self.get_settings() or {}
            mode = s.get("mode", "color")
            self.color_row.set_visible(mode == "color")
            self.scene_selector.set_visible(mode == "scene")
            
        self.device_selector.connect("notify::selected-item", on_device_changed)
        self.mode_selector.connect("notify::selected-item", on_mode_changed)
        self.color_button.connect("color-set", on_color_set)
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
            
        # Initialize visibility
        update_visibility()
            
        return [
            self.device_selector,
            self.mode_selector,
            self.color_row,
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
        mode = settings.get("mode", "color")
        
        if not device_id or not sku:
            logger.warning("Action triggered but device is not configured.")
            return
            
        client = self.plugin_base.govee_client
        if not client or not client.api_key:
            logger.warning("Action triggered but Govee client is not configured.")
            return

        try:
            if mode == "color":
                hex_str = settings.get("color_hex", "#FFFFFF").lstrip('#')
                # Convert hex to integer
                try:
                    color_val = int(hex_str, 16)
                except ValueError:
                    logger.warning(f"Invalid hex color format: {hex_str}, defaulting to white")
                    color_val = 16777215 # White
                
                logger.info(f"Setting device {device_id} ({sku}) color to {hex_str} (value: {color_val})")
                client.control_device(device_id, sku, "devices.capabilities.color_setting", "colorRgb", color_val)
                
            elif mode == "scene":
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
            logger.error(f"Error executing Govee action: {e}")
