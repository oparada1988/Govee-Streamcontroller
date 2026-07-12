# Govee Plugin for StreamController

<img src="assets/thumbnail.png" width="128" height="128" align="right" alt="Govee Plugin Thumbnail" />

Control your Govee smart lights and appliances directly from your StreamDeck or StreamController deck! This plugin integrates natively with the Govee Developer API to provide real-time control, feedback, and beautiful dynamic lighting visuals directly on your physical keys.

---

## 🌟 Key Features

The plugin provides a suite of standalone, optimized actions for complete control over your lighting setup.

### 🔌 1. Power Toggle
<img src="assets/govee.png" width="64" height="64" alt="Power Toggle Icon" />

Turn your Govee devices ON or OFF with a single keypress.
* **Dynamic Feedback**: Displays **`ON`** or **`OFF`** as the bottom label, updating in real-time.
* **Live Status Query**: Automatically checks the current device power state on layout startup.
* **Custom Labels**: Automatically sets the Govee device name as the default top label, which you can easily modify directly from StreamController's native label editor.

---

### 🔆 2. Brightness / Temp
<img src="assets/brightness-temperature-transparent.png" width="64" height="64" alt="Brightness / Temperature Icon" />

A versatile range action that supports controlling either device brightness or white color temperature.
* **Dynamic Glow & Kelvin Backgrounds**:
  * **Brightness Mode**: The key background shifts color based on value, from a dark standby shade at `0%` to a warm, glowing yellow-white at `100%`.
  * **Color Temperature Mode**: The key background transitions across the Kelvin spectrum from deep warm orange (`2,000 K`) to neutral white (`4,000 K`) and cool daylight blue (`9,000 K`).
* **Real-time Value Labels**: Displays the active value (e.g. **`85%`** or **`2,700 K`**) as the bottom label on the physical key.
* **Dial Rotations & Custom Steps**: Full support for dial controllers. Rotate the dial to step brightness or temperature up/down, and press the dial to toggle device power.
* **Gtk.Scale Sliders**: Replaces generic text inputs with clean, visual GTK slider bars in the configuration panel.

---

### 🎨 3. Set Color
<img src="assets/color_transparent.png" width="64" height="64" alt="Set Color Icon" />

Apply any solid color natively to your Govee lights.
* **Native Color Picker**: Pick colors using a native Gtk Color Button widget.
* **Dynamic Background Match**: The key background color dynamically changes on your deck to match the selected color, overlaying white transparent circles.
* **Hex Code Indicator**: Automatically displays the selected color hex code (e.g. **`#FF5E00`**) as the bottom label.

---

### 🎬 4. Apply Scene
<img src="assets/scene.png" width="64" height="64" alt="Apply Scene Icon" />

Fetch and apply any dynamic Govee scene in real-time.
* **Dynamic Scene Loading**: Queries the Govee API to fetch the list of dynamic scenes supported specifically by your selected device model.
* **Automatic Bottom Label**: Shows the chosen scene name (e.g. **`Aurora`**, **`Sunset`**) as the bottom label.

---

## 🛠️ Configuration & Setup

1. **Obtain your Govee Developer API Key**: Request your key inside the Govee Home mobile app under *User Center* -> *Developer Website*.
2. **Configure the Plugin Settings**: Paste your API key under the global **Govee Plugin Settings** page in the StreamController settings panel. If missing, the plugin will automatically prompt you for it when configuring an action.
3. **Customize your Keys**: Drag any Govee action to your deck, select your device from the populated dropdown lists, and customize the top label using StreamController's default label settings!
