# Import StreamController modules
from src.backend.PluginManager.ActionBase import ActionBase
from src.backend.DeckManagement.DeckController import DeckController
from src.backend.PageManagement.Page import Page
from src.backend.PluginManager.PluginBase import PluginBase

# Import python modules
import os
from loguru import logger
import threading
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib

class SimpleAction(ActionBase):
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
        
        # 2. Action Type ComboRow (Toggle, Turn On, Turn Off, Set Color, Apply Scene)
        self.action_type_model = Gtk.StringList()
        self.action_type_model.append("Toggle Power")
        self.action_type_model.append("Turn On")
        self.action_type_model.append("Turn Off")
        self.action_type_model.append("Set Color")
        self.action_type_model.append("Apply Scene")
        
        self.action_type_selector = Adw.ComboRow(
            model=self.action_type_model,
            title="Action Type"
        )
        current_action_type = settings.get("action_type", "toggle")
        action_type_idx = {"toggle": 0, "on": 1, "off": 2, "color": 3, "scene": 4}.get(current_action_type, 0)
        self.action_type_selector.set_selected(action_type_idx)
        
        # 3. Color EntryRow (Blank by default)
        self.color_entry = Adw.EntryRow(
            title="Color Hex (e.g. #FF0000)",
            text=settings.get("color_hex", "")
        )
        
        # 4. Scene ComboRow (Blank default option by default)
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
        
        # Build maps
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
                
                # Prepend the blank default option as requested
                scene_list_model.append("Select a Scene...")
                self.scenes_map.append(("Select a Scene...", None))
                
                if scenes:
                    for idx, scene in enumerate(scenes):
                        name = scene.get("name", "Unnamed Scene")
                        val = scene.get("value", {}) # dict with paramId, id
                        scene_list_model.append(name)
                        self.scenes_map.append((name, val))
                        
                        # Match current saved scene
                        if current_scene_id is not None and str(val.get("id")) == str(current_scene_id):
                            # Offset by 1 because we prepended "Select a Scene..."
                            selected_scene_idx = idx + 1
                            
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
                # Fetch scenes if the action mode is currently set to Scene
                s = self.get_settings() or {}
                if s.get("action_type") == "scene":
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
                    if s.get("action_type") == "scene":
                        trigger_scenes_fetch()
                    
        def on_action_type_changed(combo, *args):
            idx = combo.get_selected()
            action_type = ["toggle", "on", "off", "color", "scene"][idx]
            s = self.get_settings()
            s["action_type"] = action_type
            self.set_settings(s)
            update_visibility()
            if action_type == "scene" and not self.scenes_map:
                trigger_scenes_fetch()
                    
        def on_color_changed(entry, *args):
            text = entry.get_text().strip()
            s = self.get_settings()
            s["color_hex"] = text
            self.set_settings(s)

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
                    # Selected "Select a Scene..." (blank option)
                    s["scene_name"] = ""
                    s["scene_id"] = None
                    s["scene_param_id"] = None
                self.set_settings(s)
            
        def on_refresh_clicked(button):
            self.refresh_button.set_sensitive(False)
            def on_refresh_done(devices):
                populate_devices(devices)
                s = self.get_settings() or {}
                if s.get("action_type") == "scene":
                    trigger_scenes_fetch(force_refresh=True)
                self.refresh_button.set_sensitive(True)
            self.plugin_base.fetch_devices_async(on_refresh_done, force_refresh=True)

        def update_visibility():
            s = self.get_settings() or {}
            action_type = s.get("action_type", "toggle")
            self.color_entry.set_visible(action_type == "color")
            self.scene_selector.set_visible(action_type == "scene")
            
        self.device_selector.connect("notify::selected-item", on_device_changed)
        self.action_type_selector.connect("notify::selected-item", on_action_type_changed)
        self.color_entry.connect("notify::text", on_color_changed)
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
            self.action_type_selector,
            self.color_entry,
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
        action_type = settings.get("action_type", "toggle")
        
        if not device_id or not sku:
            logger.warning("Action triggered but device is not configured.")
            return
            
        client = self.plugin_base.govee_client
        if not client or not client.api_key:
            logger.warning("Action triggered but Govee client is not configured.")
            return

        try:
            if action_type == "on":
                logger.info(f"Turning ON device {device_id} ({sku})")
                client.control_device(device_id, sku, "devices.capabilities.on_off", "powerSwitch", 1)
            elif action_type == "off":
                logger.info(f"Turning OFF device {device_id} ({sku})")
                client.control_device(device_id, sku, "devices.capabilities.on_off", "powerSwitch", 0)
            elif action_type == "toggle":
                logger.info(f"Toggling power state for device {device_id} ({sku})")
                # 1. Fetch current state
                state_data = client.get_device_state(device_id, sku)
                current_power = None
                if state_data:
                    capabilities = state_data.get("capabilities", [])
                    for cap in capabilities:
                        if (cap.get("type") == "devices.capabilities.on_off" and 
                            cap.get("instance") == "powerSwitch"):
                            current_power = cap.get("state", {}).get("value")
                            break
                
                # 2. Toggle power based on current state (default to turning on if state unknown)
                target_value = 0 if current_power == 1 else 1
                logger.info(f"Current power state: {current_power}, sending value: {target_value}")
                client.control_device(device_id, sku, "devices.capabilities.on_off", "powerSwitch", target_value)
            elif action_type == "color":
                hex_str = settings.get("color_hex", "").strip().lstrip('#')
                if not hex_str:
                    logger.warning("Action triggered (Set Color) but no color is configured.")
                    return
                try:
                    color_val = int(hex_str, 16)
                except ValueError:
                    logger.warning(f"Invalid hex color format: {hex_str}")
                    return
                
                logger.info(f"Setting device {device_id} ({sku}) color to {hex_str} (value: {color_val})")
                client.control_device(device_id, sku, "devices.capabilities.color_setting", "colorRgb", color_val)
            elif action_type == "scene":
                scene_id = settings.get("scene_id")
                param_id = settings.get("scene_param_id")
                scene_name = settings.get("scene_name", "")
                
                if scene_id is None or param_id is None:
                    logger.warning("Action triggered (Apply Scene) but no scene is selected.")
                    return
                    
                value = {
                    "id": int(scene_id),
                    "paramId": int(param_id)
                }
                logger.info(f"Applying scene '{scene_name}' (value: {value}) to device {device_id} ({sku})")
                client.control_device(device_id, sku, "devices.capabilities.dynamic_scene", "lightScene", value)
        except Exception as e:
            logger.error(f"Error executing Govee action: {e}")