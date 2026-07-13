# Import StreamController modules
from src.backend.PluginManager.ActionBase import ActionBase
from src.backend.DeckManagement.InputIdentifier import Input, InputEvent

# Import python modules
import os
from loguru import logger
import threading
import time
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib

def kelvin_to_rgb(kelvin: int) -> tuple[int, int, int]:
    # Linear interpolation between known points
    # 2000K -> (255, 137, 18)
    # 2700K -> (255, 166, 81)
    # 4000K -> (255, 209, 163)
    # 6500K -> (255, 255, 255)
    # 9000K -> (190, 215, 255)
    if kelvin <= 2000:
        return (255, 137, 18)
    elif kelvin <= 2700:
        t = (kelvin - 2000) / 700.0
        return (255, int(137 + t * (166 - 137)), int(18 + t * (81 - 18)))
    elif kelvin <= 4000:
        t = (kelvin - 2700) / 1300.0
        return (255, int(166 + t * (209 - 166)), int(81 + t * (163 - 81)))
    elif kelvin <= 6500:
        t = (kelvin - 4000) / 2500.0
        return (255, int(209 + t * (255 - 209)), int(163 + t * (255 - 163)))
    elif kelvin <= 9000:
        t = (kelvin - 6500) / 2500.0
        return (int(255 - t * (255 - 190)), int(255 - t * (255 - 215)), 255)
    else:
        return (190, 215, 255)

def brightness_to_rgb(brightness: int) -> tuple[int, int, int]:
    # Interpolate between dark standby (35, 35, 40) and warm glow (255, 235, 150)
    b = max(0, min(100, brightness)) / 100.0
    r = int(35 + (255 - 35) * b)
    g = int(35 + (235 - 35) * b)
    b_val = int(40 + (150 - 40) * b)
    return (r, g, b_val)

class BrightnessAction(ActionBase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.devices_map = []
        self.current_brightness = 50
        self.current_temperature = 4000
        self.debounce_timer_id = 0
        self.last_api_call_time = 0.0
        
    def on_ready(self) -> None:
        icon_path = os.path.join(self.plugin_base.PATH, "assets", "brightness-temperature-transparent.png")
        self.set_media(media_path=icon_path, size=1.0)
        
        # Set top label to device name by default if not set, or re-apply cached label
        current_top = self.labels.get("top", {}).get("text", "")
        if not current_top:
            settings = self.get_settings() or {}
            dev_name = settings.get("device_name", "")
            if dev_name:
                self.set_top_label(dev_name)
        else:
            self.set_top_label(current_top)
        
        # Initialize background color & bottom label visuals
        self.update_visuals()

        # Check Govee API Key configuration
        self.plugin_base.prompt_api_key_if_missing()
        
        # Load initial device status in background
        threading.Thread(target=self._fetch_initial_state, daemon=True).start()

    def update_visuals(self) -> None:
        settings = self.get_settings() or {}
        mode = settings.get("control_mode", "brightness")
        
        if mode == "brightness":
            val = getattr(self, "current_brightness", settings.get("target_brightness", 100))
            r, g, b = brightness_to_rgb(val)
            self.set_background_color(color=[r, g, b, 255])
            self.set_bottom_label(f"{val}%")
        else:
            val = getattr(self, "current_temperature", settings.get("target_temperature", 4000))
            r, g, b = kelvin_to_rgb(val)
            self.set_background_color(color=[r, g, b, 255])
            self.set_bottom_label(f"{val:,} K")

    def get_step_size(self) -> int:
        settings = self.get_settings() or {}
        mode = settings.get("control_mode", "brightness")
        if mode == "brightness":
            try:
                return int(settings.get("step_brightness", 10))
            except (ValueError, TypeError):
                return 10
        else:
            try:
                return int(settings.get("step_temperature", 500))
            except (ValueError, TypeError):
                return 500

    def get_target_value(self) -> int:
        settings = self.get_settings() or {}
        mode = settings.get("control_mode", "brightness")
        if mode == "brightness":
            try:
                return int(settings.get("target_brightness", 100))
            except (ValueError, TypeError):
                return 100
        else:
            try:
                return int(settings.get("target_temperature", 4000))
            except (ValueError, TypeError):
                return 4000

    def get_config_rows(self) -> list:
        # Load settings
        settings = self.get_settings() or {}
        
        # 1. Device ComboRow
        self.device_model = Gtk.StringList()
        self.device_selector = Adw.ComboRow(
            model=self.device_model,
            title="Govee Device"
        )
        
        # 2. Control Mode Dropdown
        self.control_mode_model = Gtk.StringList()
        self.control_mode_model.append("Brightness")
        self.control_mode_model.append("Color Temperature")
        
        self.control_mode_selector = Adw.ComboRow(
            model=self.control_mode_model,
            title="Control Mode"
        )
        current_mode = settings.get("control_mode", "brightness")
        mode_idx = 0 if current_mode == "brightness" else 1
        self.control_mode_selector.set_selected(mode_idx)

        # 3. Brightness Slider Group
        self.brightness_slider = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 1)
        self.brightness_slider.set_value(settings.get("target_brightness", 100))
        self.brightness_slider.set_size_request(200, -1)
        self.brightness_slider.set_valign(Gtk.Align.CENTER)
        
        self.brightness_target_row = Adw.ActionRow(
            title="Target Brightness (0-100)"
        )
        self.brightness_target_row.add_suffix(self.brightness_slider)
        
        self.brightness_step_slider = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 1, 50, 1)
        self.brightness_step_slider.set_value(settings.get("step_brightness", 10))
        self.brightness_step_slider.set_size_request(200, -1)
        self.brightness_step_slider.set_valign(Gtk.Align.CENTER)
        
        self.brightness_step_row = Adw.ActionRow(
            title="Dial Step Size (1-50)"
        )
        self.brightness_step_row.add_suffix(self.brightness_step_slider)

        # 4. Color Temperature Slider Group
        self.temp_slider = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 2000, 9000, 100)
        self.temp_slider.set_value(settings.get("target_temperature", 4000))
        self.temp_slider.set_size_request(200, -1)
        self.temp_slider.set_valign(Gtk.Align.CENTER)
        
        self.temp_target_row = Adw.ActionRow(
            title="Target Temperature (2000-9000 K)"
        )
        self.temp_target_row.add_suffix(self.temp_slider)
        
        self.temp_step_slider = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 100, 1000, 50)
        self.temp_step_slider.set_value(settings.get("step_temperature", 500))
        self.temp_step_slider.set_size_request(200, -1)
        self.temp_step_slider.set_valign(Gtk.Align.CENTER)
        
        self.temp_step_row = Adw.ActionRow(
            title="Dial Step Size (100-1000 K)"
        )
        self.temp_step_row.add_suffix(self.temp_step_slider)
        
        # 5. Refresh Devices row & button
        self.refresh_button = Gtk.Button.new_from_icon_name("view-refresh-symbolic")
        self.refresh_button.set_valign(Gtk.Align.CENTER)
        self.refresh_button.set_tooltip_text("Refresh Govee Devices")
        
        self.refresh_row = Adw.ActionRow(
            title="Refresh Device List",
            subtitle="Query the Govee API for updated devices"
        )
        self.refresh_row.add_suffix(self.refresh_button)
        
        # Build devices map
        self.devices_map = []
        
        # Populating function
        def populate_dropdown(devices):
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

        # Visibility helper
        def update_visibility():
            s = self.get_settings() or {}
            mode = s.get("control_mode", "brightness")
            is_brightness = (mode == "brightness")
            
            self.brightness_target_row.set_visible(is_brightness)
            self.brightness_step_row.set_visible(is_brightness)
            self.temp_target_row.set_visible(not is_brightness)
            self.temp_step_row.set_visible(not is_brightness)

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
                    self.update_visuals()
                    # Fetch new device's initial state
                    threading.Thread(target=self._fetch_initial_state, daemon=True).start()

        def on_mode_changed(combo, *args):
            idx = combo.get_selected()
            mode = "brightness" if idx == 0 else "temperature"
            s = self.get_settings()
            s["control_mode"] = mode
            self.set_settings(s)
            update_visibility()
            self.update_visuals()
            # Fetch new mode status
            threading.Thread(target=self._fetch_initial_state, daemon=True).start()

        def on_brightness_slider_changed(scale):
            val = int(scale.get_value())
            s = self.get_settings()
            s["target_brightness"] = val
            self.set_settings(s)
            self.current_brightness = val
            self.update_visuals()

        def on_brightness_step_changed(scale):
            val = int(scale.get_value())
            s = self.get_settings()
            s["step_brightness"] = val
            self.set_settings(s)

        def on_temp_slider_changed(scale):
            val = int(scale.get_value())
            s = self.get_settings()
            s["target_temperature"] = val
            self.set_settings(s)
            self.current_temperature = val
            self.update_visuals()

        def on_temp_step_changed(scale):
            val = int(scale.get_value())
            s = self.get_settings()
            s["step_temperature"] = val
            self.set_settings(s)
            
        def on_refresh_clicked(button):
            self.refresh_button.set_sensitive(False)
            def on_refresh_done(devices):
                populate_dropdown(devices)
                self.refresh_button.set_sensitive(True)
            self.plugin_base.fetch_devices_async(on_refresh_done, force_refresh=True)
            
        self.device_selector.connect("notify::selected-item", on_device_changed)
        self.control_mode_selector.connect("notify::selected-item", on_mode_changed)
        self.brightness_slider.connect("value-changed", on_brightness_slider_changed)
        self.brightness_step_slider.connect("value-changed", on_brightness_step_changed)
        self.temp_slider.connect("value-changed", on_temp_slider_changed)
        self.temp_step_slider.connect("value-changed", on_temp_step_changed)
        self.refresh_button.connect("clicked", on_refresh_clicked)
        
        # Populate initial list using cache or fetch if empty
        if self.plugin_base.devices:
            populate_dropdown(self.plugin_base.devices)
        else:
            new_model = Gtk.StringList()
            new_model.append("Loading devices...")
            self.device_selector.set_model(new_model)
            
            api_key = self.plugin_base.get_settings().get("api_key", "")
            if not api_key:
                self.plugin_base.prompt_api_key_if_missing(callback=populate_dropdown)
            else:
                self.plugin_base.fetch_devices_async(populate_dropdown)
            
        # Initial visibility settings
        update_visibility()
            
        return [
            self.device_selector,
            self.control_mode_selector,
            self.brightness_target_row,
            self.brightness_step_row,
            self.temp_target_row,
            self.temp_step_row,
            self.refresh_row
        ]

    def _fetch_initial_state(self):
        settings = self.get_settings()
        device_id = settings.get("device_id")
        sku = settings.get("device_sku")
        if not device_id or not sku:
            return
        client = self.plugin_base.govee_client
        if not client or not client.api_key:
            return
            
        try:
            state = client.get_device_state(device_id, sku)
            if state:
                capabilities = state.get("capabilities", [])
                for cap in capabilities:
                    cap_type = cap.get("type")
                    instance = cap.get("instance")
                    val = cap.get("state", {}).get("value")
                    
                    if cap_type == "devices.capabilities.range" and instance == "brightness":
                        self.current_brightness = int(val if val is not None else 50)
                        logger.info(f"Fetched initial brightness: {self.current_brightness}")
                    elif cap_type == "devices.capabilities.color_setting" and instance == "colorTemperatureK":
                        self.current_temperature = int(val if val is not None else 4000)
                        logger.info(f"Fetched initial temperature: {self.current_temperature}")
                
                # Dynamically update the GUI visuals on successful fetch
                GLib.idle_add(self.update_visuals)
        except Exception as e:
            logger.error(f"Error fetching initial device state: {e}")

    def on_key_down(self) -> None:
        threading.Thread(target=self._send_static_value, daemon=True).start()

    def on_key_up(self) -> None:
        pass

    def event_callback(self, event: InputEvent, data: dict = None):
        if event == Input.Dial.Events.TURN_CW:
            self.adjust_range(self.get_step_size())
        elif event == Input.Dial.Events.TURN_CCW:
            self.adjust_range(-self.get_step_size())
        elif event == Input.Dial.Events.DOWN:
            self.toggle_power()
        else:
            super().event_callback(event, data)

    def adjust_range(self, delta: int):
        settings = self.get_settings() or {}
        mode = settings.get("control_mode", "brightness")
        
        if mode == "brightness":
            self.current_brightness = max(0, min(100, self.current_brightness + delta))
            logger.info(f"Local brightness adjusted to: {self.current_brightness}")
            target_value = self.current_brightness
        else:
            self.current_temperature = max(2000, min(9000, self.current_temperature + delta))
            logger.info(f"Local temperature adjusted to: {self.current_temperature}")
            target_value = self.current_temperature

        # Instantly update key background & bottom label values in real-time
        self.update_visuals()

        if self.debounce_timer_id:
            GLib.source_remove(self.debounce_timer_id)
            
        def do_api_call():
            now = time.time()
            time_since_last = now - getattr(self, "last_api_call_time", 0.0)
            if time_since_last < 0.5:  # Enforce 500ms minimum interval (2 requests/sec)
                # Reschedule to execute exactly when the 500ms window has passed
                wait_time_ms = int((0.5 - time_since_last) * 1000)
                self.debounce_timer_id = GLib.timeout_add(wait_time_ms, do_api_call)
                return False
                
            self.last_api_call_time = now
            threading.Thread(target=self._send_range_api, args=(mode, target_value), daemon=True).start()
            self.debounce_timer_id = 0
            return False
            
        self.debounce_timer_id = GLib.timeout_add(150, do_api_call)

    def _send_range_api(self, mode: str, value: int):
        settings = self.get_settings()
        device_id = settings.get("device_id")
        sku = settings.get("device_sku")
        if not device_id or not sku:
            return
        client = self.plugin_base.govee_client
        if not client:
            return
            
        if mode == "brightness":
            client.control_device(device_id, sku, "devices.capabilities.range", "brightness", value)
        else:
            client.control_device(device_id, sku, "devices.capabilities.color_setting", "colorTemperatureK", value)

    def _send_static_value(self):
        settings = self.get_settings() or {}
        mode = settings.get("control_mode", "brightness")
        target = self.get_target_value()
        
        logger.info(f"Setting static {mode} value to {target}")
        self._send_range_api(mode, target)
        
        # Update local cache
        if mode == "brightness":
            self.current_brightness = target
        else:
            self.current_temperature = target
            
        # Update visuals
        self.update_visuals()

    def toggle_power(self):
        threading.Thread(target=self._execute_toggle_power, daemon=True).start()

    def _execute_toggle_power(self):
        settings = self.get_settings()
        device_id = settings.get("device_id")
        sku = settings.get("device_sku")
        if not device_id or not sku:
            return
        client = self.plugin_base.govee_client
        if not client:
            return
        try:
            state_data = client.get_device_state(device_id, sku)
            current_power = None
            if state_data:
                capabilities = state_data.get("capabilities", [])
                for cap in capabilities:
                    if (cap.get("type") == "devices.capabilities.on_off" and 
                        cap.get("instance") == "powerSwitch"):
                        current_power = cap.get("state", {}).get("value")
                        break
            
            target_value = 0 if current_power == 1 else 1
            client.control_device(device_id, sku, "devices.capabilities.on_off", "powerSwitch", target_value)
        except Exception as e:
            logger.error(f"Error toggling power: {e}")
