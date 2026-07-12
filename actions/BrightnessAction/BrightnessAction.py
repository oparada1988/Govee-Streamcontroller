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

class BrightnessAction(ActionBase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.devices_map = []
        self.current_brightness = 50
        self.debounce_timer_id = 0
        
    def on_ready(self) -> None:
        icon_path = os.path.join(self.plugin_base.PATH, "assets", "info.png")
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
        
        # Load initial brightness status in background
        threading.Thread(target=self._fetch_initial_state, daemon=True).start()

    def get_step_size(self) -> int:
        settings = self.get_settings() or {}
        try:
            return int(settings.get("step_size", 10))
        except (ValueError, TypeError):
            return 10

    def get_target_brightness(self) -> int:
        settings = self.get_settings() or {}
        try:
            return int(settings.get("target_brightness", 100))
        except (ValueError, TypeError):
            return 100

    def get_config_rows(self) -> list:
        # Load settings
        settings = self.get_settings() or {}
        
        # 1. Device ComboRow
        self.device_model = Gtk.StringList()
        self.device_selector = Adw.ComboRow(
            model=self.device_model,
            title="Govee Device"
        )
        
        # 2. Target Brightness Row (For Buttons)
        self.brightness_entry = Adw.EntryRow(
            title="Target Brightness (0-100)",
            text=str(settings.get("target_brightness", 100))
        )
        
        # 3. Step Size Row (For Dials)
        self.step_entry = Adw.EntryRow(
            title="Dial Step Size (1-100)",
            text=str(settings.get("step_size", 10))
        )
        
        # 4. Refresh Devices row & button
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
                    # Fetch new device's initial state
                    threading.Thread(target=self._fetch_initial_state, daemon=True).start()
                    
        def on_brightness_changed(entry, *args):
            text = entry.get_text().strip()
            try:
                val = int(text)
                if 0 <= val <= 100:
                    s = self.get_settings()
                    s["target_brightness"] = val
                    self.set_settings(s)
            except ValueError:
                pass

        def on_step_changed(entry, *args):
            text = entry.get_text().strip()
            try:
                val = int(text)
                if 1 <= val <= 100:
                    s = self.get_settings()
                    s["step_size"] = val
                    self.set_settings(s)
            except ValueError:
                pass
            
        def on_refresh_clicked(button):
            self.refresh_button.set_sensitive(False)
            def on_refresh_done(devices):
                populate_dropdown(devices)
                self.refresh_button.set_sensitive(True)
            self.plugin_base.fetch_devices_async(on_refresh_done, force_refresh=True)
            
        self.device_selector.connect("notify::selected-item", on_device_changed)
        self.brightness_entry.connect("notify::text", on_brightness_changed)
        self.step_entry.connect("notify::text", on_step_changed)
        self.refresh_button.connect("clicked", on_refresh_clicked)
        
        # Populate initial list using cache or fetch if empty
        if self.plugin_base.devices:
            populate_dropdown(self.plugin_base.devices)
        else:
            new_model = Gtk.StringList()
            new_model.append("Loading devices...")
            self.device_selector.set_model(new_model)
            self.plugin_base.fetch_devices_async(populate_dropdown)
            
        return [
            self.device_selector,
            self.brightness_entry,
            self.step_entry,
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
                    if (cap.get("type") == "devices.capabilities.range" and 
                        cap.get("instance") == "brightness"):
                        self.current_brightness = int(cap.get("state", {}).get("value", 50))
                        logger.info(f"Fetched initial brightness: {self.current_brightness}")
                        break
        except Exception as e:
            logger.error(f"Error fetching initial brightness: {e}")

    def on_key_down(self) -> None:
        threading.Thread(target=self._send_static_brightness, daemon=True).start()

    def on_key_up(self) -> None:
        pass

    def event_callback(self, event: InputEvent, data: dict = None):
        if event == Input.Dial.Events.TURN_CW:
            self.adjust_brightness(self.get_step_size())
        elif event == Input.Dial.Events.TURN_CCW:
            self.adjust_brightness(-self.get_step_size())
        elif event == Input.Dial.Events.DOWN:
            self.toggle_power()
        else:
            super().event_callback(event, data)

    def adjust_brightness(self, delta: int):
        self.current_brightness = max(0, min(100, self.current_brightness + delta))
        logger.info(f"Local brightness adjusted to: {self.current_brightness}")
        
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
            threading.Thread(target=self._send_brightness_api, args=(self.current_brightness,), daemon=True).start()
            self.debounce_timer_id = 0
            return False
            
        self.debounce_timer_id = GLib.timeout_add(150, do_api_call)

    def _send_brightness_api(self, value: int):
        settings = self.get_settings()
        device_id = settings.get("device_id")
        sku = settings.get("device_sku")
        if not device_id or not sku:
            return
        client = self.plugin_base.govee_client
        if client:
            client.control_device(device_id, sku, "devices.capabilities.range", "brightness", value)

    def _send_static_brightness(self):
        target = self.get_target_brightness()
        logger.info(f"Setting static brightness to {target}")
        self._send_brightness_api(target)
        # Update local cache
        self.current_brightness = target

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
