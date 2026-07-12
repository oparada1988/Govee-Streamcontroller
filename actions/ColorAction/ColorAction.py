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

class ColorAction(ActionBase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.devices_map = []
        
    def on_ready(self) -> None:
        icon_path = os.path.join(self.plugin_base.PATH, "assets", "color.png")
        self.set_media(media_path=icon_path, size=0.75)

        # Set top label to device name by default if not set
        current_top = self.labels.get("top", {}).get("text", "")
        if not current_top:
            settings = self.get_settings() or {}
            dev_name = settings.get("device_name", "")
            if dev_name:
                self.set_top_label(dev_name)

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
        
        # 2. Color Picker Button inside an ActionRow
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
        
        # 3. Refresh Devices row & button
        self.refresh_button = Gtk.Button.new_from_icon_name("view-refresh-symbolic")
        self.refresh_button.set_valign(Gtk.Align.CENTER)
        self.refresh_button.set_tooltip_text("Refresh Govee Devices")
        
        self.refresh_row = Adw.ActionRow(
            title="Refresh Devices",
            subtitle="Force update devices list"
        )
        self.refresh_row.add_suffix(self.refresh_button)
        
        # Build devices map
        self.devices_map = []
        
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
                    
        def on_color_set(button):
            rgba = button.get_rgba()
            r = int(rgba.red * 255)
            g = int(rgba.green * 255)
            b = int(rgba.blue * 255)
            hex_color = f"#{r:02X}{g:02X}{b:02X}"
            s = self.get_settings()
            s["color_hex"] = hex_color
            self.set_settings(s)

        def on_refresh_clicked(button):
            self.refresh_button.set_sensitive(False)
            def on_refresh_done(devices):
                populate_devices(devices)
                self.refresh_button.set_sensitive(True)
            self.plugin_base.fetch_devices_async(on_refresh_done, force_refresh=True)
            
        self.device_selector.connect("notify::selected-item", on_device_changed)
        self.color_button.connect("color-set", on_color_set)
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
            hex_str = settings.get("color_hex", "#FFFFFF").lstrip('#')
            # Convert hex to integer
            try:
                color_val = int(hex_str, 16)
            except ValueError:
                logger.warning(f"Invalid hex color format: {hex_str}, defaulting to white")
                color_val = 16777215 # White
            
            logger.info(f"Setting device {device_id} ({sku}) color to {hex_str} (value: {color_val})")
            client.control_device(device_id, sku, "devices.capabilities.color_setting", "colorRgb", color_val)
                
        except Exception as e:
            logger.error(f"Error executing Govee color action: {e}")
