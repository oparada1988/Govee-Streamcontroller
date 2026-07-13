# Import StreamController modules
from src.backend.PluginManager.ActionBase import ActionBase

# Import python modules
import os
from loguru import logger
import threading
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib, Gdk

class SceneAction(ActionBase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.devices_map = []
        self.scenes_map = []
        
    def _update_background_color(self, scene_name: str, manual_hex: str = None) -> None:
        if manual_hex and manual_hex.startswith("#"):
            hex_clean = manual_hex.lstrip('#')
            try:
                r = int(hex_clean[0:2], 16)
                g = int(hex_clean[2:4], 16)
                b = int(hex_clean[4:6], 16)
                self.set_background_color(color=[r, g, b, 255])
                return
            except Exception as e:
                logger.error(f"Error parsing manual hex color {manual_hex}: {e}")

        if not scene_name:
            self.set_background_color(color=[30, 41, 59, 255])
            return

        name_lower = scene_name.lower()
        color_map = {
            ("sunset", "sunrise", "dawn", "morning", "sun"): [235, 94, 40, 255],        # Warm orange
            ("ocean", "water", "sea", "rain", "deep", "blue"): [14, 116, 144, 255],      # Ocean cyan/blue
            ("forest", "garden", "nature", "grass", "green", "leaves"): [21, 128, 61, 255], # Forest green
            ("movie", "cinema", "theater", "gaming", "game"): [109, 40, 217, 255],      # Movie purple
            ("rainbow", "colorful", "party", "dance", "disco"): [192, 38, 211, 255],    # Party magenta
            ("candle", "fire", "cozy", "warm", "amber"): [194, 65, 12, 255],            # Cozy amber/red-orange
            ("night", "sleep", "starry", "dream", "bed"): [30, 27, 75, 255],             # Night indigo
            ("lightning", "storm", "thunder"): [79, 70, 229, 255],                       # Storm electric indigo
            ("sakura", "flower", "blossom", "pink", "rose"): [219, 39, 119, 255],       # Pink
            ("aurora", "magic", "teal"): [13, 148, 136, 255],                            # Teal/aurora
        }

        matched_color = None
        for keywords, color in color_map.items():
            if any(kw in name_lower for kw in keywords):
                matched_color = color
                break

        if matched_color:
            self.set_background_color(color=matched_color)
        else:
            self.set_background_color(color=[15, 118, 110, 255]) # Default Govee theme teal/blue

    def on_ready(self) -> None:
        icon_path = os.path.join(self.plugin_base.PATH, "assets", "scene.png")
        self.set_media(media_path=icon_path, size=1.0)

        # Set labels to device/scene names by default if not set
        current_top = self.labels.get("top", {}).get("text", "")
        if not current_top:
            settings = self.get_settings() or {}
            dev_name = settings.get("device_name", "")
            if dev_name:
                self.set_top_label(dev_name)

        current_bottom = self.labels.get("bottom", {}).get("text", "")
        if not current_bottom:
            settings = self.get_settings() or {}
            scene_name = settings.get("scene_name", "")
            if scene_name:
                self.set_bottom_label(scene_name)

        # Update background color dynamically
        settings = self.get_settings() or {}
        scene_name = settings.get("scene_name", "")
        use_override = settings.get("override_color", False)
        manual_hex = settings.get("color_hex", "#FFFFFF") if use_override else None
        self._update_background_color(scene_name, manual_hex)

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
        
        # 2. Scene ComboRow
        self.scene_model = Gtk.StringList()
        self.scene_selector = Adw.ComboRow(
            model=self.scene_model,
            title="Select Scene"
        )

        # 3. Override switch
        self.override_switch = Gtk.Switch()
        self.override_switch.set_valign(Gtk.Align.CENTER)
        self.override_switch.set_active(settings.get("override_color", False))
        
        self.override_row = Adw.ActionRow(
            title="Manual Color Override",
            subtitle="Manually override the automatic scene background color"
        )
        self.override_row.add_suffix(self.override_switch)
        
        # 4. Color Picker Button inside an ActionRow
        self.color_button = Gtk.ColorButton()
        self.color_button.set_valign(Gtk.Align.CENTER)
        
        # Parse initial color
        current_color = settings.get("color_hex", "#FFFFFF")
        rgba = Gdk.RGBA()
        rgba.parse(current_color)
        self.color_button.set_rgba(rgba)
        
        self.color_row = Adw.ActionRow(
            title="Custom Key Color",
            subtitle="Click the color block to pick a custom background color"
        )
        self.color_row.add_suffix(self.color_button)
        
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
                    self.set_top_label(name)
                    trigger_scenes_fetch()
                    
        def on_scene_changed(combo, *args):
            idx = combo.get_selected()
            if 0 <= idx < len(self.scenes_map):
                name, val = self.scenes_map[idx]
                s = self.get_settings()
                if val:
                    s["scene_name"] = name
                    s["scene_id"] = val.get("id")
                    s["scene_param_id"] = val.get("paramId")
                    self.set_bottom_label(name)
                else:
                    s["scene_name"] = ""
                    s["scene_id"] = None
                    s["scene_param_id"] = None
                    self.set_bottom_label("")
                self.set_settings(s)
                
                # Update background color dynamically when scene changes
                active = s.get("override_color", False)
                manual_hex = s.get("color_hex", "#FFFFFF") if active else None
                self._update_background_color(s.get("scene_name", ""), manual_hex)
            
        def on_refresh_clicked(button):
            self.refresh_button.set_sensitive(False)
            def on_refresh_done(devices):
                populate_devices(devices)
                trigger_scenes_fetch(force_refresh=True)
                self.refresh_button.set_sensitive(True)
            self.plugin_base.fetch_devices_async(on_refresh_done, force_refresh=True)

        def update_color_rows_visibility():
            active = self.override_switch.get_active()
            self.color_row.set_visible(active)

        def on_override_toggled(switch, *args):
            active = switch.get_active()
            s = self.get_settings()
            s["override_color"] = active
            self.set_settings(s)
            update_color_rows_visibility()
            
            scene_name = s.get("scene_name", "")
            manual_hex = s.get("color_hex", "#FFFFFF") if active else None
            self._update_background_color(scene_name, manual_hex)

        def on_color_set(button):
            rgba = button.get_rgba()
            r = int(rgba.red * 255)
            g = int(rgba.green * 255)
            b = int(rgba.blue * 255)
            hex_color = f"#{r:02X}{g:02X}{b:02X}"
            s = self.get_settings()
            s["color_hex"] = hex_color
            self.set_settings(s)
            self.set_background_color(color=[r, g, b, 255])
            
        self.device_selector.connect("notify::selected-item", on_device_changed)
        self.scene_selector.connect("notify::selected-item", on_scene_changed)
        self.refresh_button.connect("clicked", on_refresh_clicked)
        self.override_switch.connect("notify::active", on_override_toggled)
        self.color_button.connect("color-set", on_color_set)
        
        # Populate initial list using cache or fetch if empty
        if self.plugin_base.devices:
            populate_devices(self.plugin_base.devices)
        else:
            new_model = Gtk.StringList()
            new_model.append("Loading devices...")
            self.device_selector.set_model(new_model)
            
            api_key = self.plugin_base.get_settings().get("api_key", "")
            if not api_key:
                self.plugin_base.prompt_api_key_if_missing(callback=populate_devices)
            else:
                self.plugin_base.fetch_devices_async(populate_devices)
            
        # Set initial visibility of the color row
        update_color_rows_visibility()
            
        return [
            self.device_selector,
            self.scene_selector,
            self.override_row,
            self.color_row,
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
