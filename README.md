# sta-sta-proxy: Seamless IoT & Device Control Gateway

This project configures a **MikroTik RouterBOARD (RB711UA-2HnD)** to act as a wireless Station (STA) that connects to smart devices/appliances operating in Access Point (AP) mode (such as Tasmota plugs, Rover Tanks, or other IoT configuration portals). 

By connecting the RouterBOARD's physical `ether1` interface to your regular LAN, you can control and configure these standalone AP devices directly from any computer, tablet, or phone on your primary network. You never have to disconnect from your home network or switch WiFi SSIDs again!

---

## The Core Concept: Layer 3 STA Proxy Gateway

```
  [ My PC/Phone ] (Connected to Home Network)
        │
        ▼ (Targeting 192.168.4.1 or the AP IP)
  [ Home Router / LAN Switch ] (192.168.2.x Subnet)
        │
        ▼ (Incoming via ether1)
  [ MikroTik RouterBOARD (RB711) ] (Act as STA Gateway / Router)
        │ (Wireless STA Mode / Connects to Smart Device)
        ▼ (Wireless Link)
  [ Smart Device AP ] (e.g., Tasmota, Rover Tank - 192.168.4.1)
```

1. The **Smart Device** (Tasmota, Rover Tank) hosts its own configuration/control WiFi AP (often on `192.168.4.1`).
2. The **MikroTik RouterBOARD**'s wireless interface (`wlan1`) connects to the Smart Device's AP as a client/Station (STA).
3. The RouterBOARD's physical port (`ether1`) is connected to your **Home LAN** and obtains a local IP (e.g., `192.168.2.199`).
4. **NAT/Routing Rule**: Any traffic sent from your home network targeting the Smart Device's subnet (typically `192.168.4.0/24`) is routed through the RouterBOARD (`192.168.2.199`) which NATs and proxies the request over WiFi (`wlan1`).

---

## WebFig Manual Setup Instructions

This section outlines how to configure the MikroTik RouterBOARD as an STA proxy gateway manually using the WebFig web interface.

### Step 1: Access WebFig
1. Open your browser and navigate to the RouterBOARD's LAN IP address (e.g., `http://192.168.2.199`).
2. Leave the password blank and click **Login**.

### Step 2: Configure the Wireless Interface
1. In the left-hand menu, navigate to **Wireless**.
2. Under the **WiFi Interfaces** tab, select `wlan1`.
3. Change the following parameters:
   - **Mode**: `station`
   - **Band**: `2GHz-B/G/N` (or matching your target device's specs)
   - **SSID**: Set this to the exact name of the target device's AP network (e.g., `Tasmota-XXXXXX` or `Rover-Tank`).
4. Click **Apply** or **OK**.

*Note: If the target device's AP requires a password:*
1. Navigate to **Wireless** -> **Security Profiles** tab.
2. Edit the `default` profile or add a new one:
   - **Mode**: `dynamic keys`
   - **Authentication Types**: Check `WPA PSK` and `WPA2 PSK`.
   - **Unicast Ciphers & Group Ciphers**: Check `aes-ccm` and `tkip`.
   - **WPA / WPA2 Pre-Shared Key**: Enter the target AP's WiFi password.
3. Click **OK**, then go back to `wlan1` under **WiFi Interfaces** and ensure its **Security Profile** matches.

### Step 3: Configure IP Routing & DHCP on Wireless (`wlan1`)
For the RouterBOARD to communicate with the target device, `wlan1` needs an IP address in the target device's subnet.
1. Navigate to **IP** -> **DHCP Client**.
2. Click **Add New**:
   - **Interface**: `wlan1`
   - **Use Peer DNS**: `yes`
   - **Add Default Route**: `no` (Crucial! Do not overwrite your home LAN gateway default route).
3. Click **OK**.
4. Once `wlan1` connects to the target AP, it will dynamically receive an IP lease (e.g., `192.168.4.x`).

### Step 4: Configure NAT (Masquerade)
To allow your home LAN packets to travel seamlessly through the wireless link, you must set up Source NAT (Masquerading):
1. Navigate to **IP** -> **Firewall** -> **NAT** tab.
2. Click **Add New**:
   - **Chain**: `srcnat`
   - **Out. Interface**: `wlan1`
   - **Action**: `masquerade`
3. Click **OK**.

### Step 5: Add a Route on Your Main Computer/Router
To reach the target device (e.g., `192.168.4.1`) from your PC or phone, your computer needs to know that the gateway to `192.168.4.0/24` is the RouterBOARD.

* **Option A: Add a route on your PC (recommended for individual testing):**
  - **macOS/Linux**: `sudo route -n add 192.168.4.0/24 192.168.2.199`
  - **Windows (Admin Command Prompt)**: `route add 192.168.4.0 mask 255.255.255.0 192.168.2.199`

* **Option B: Add a static route on your Home Router (recommended for network-wide access):**
  - Destination: `192.168.4.0/24` (or target subnet)
  - Gateway: The IP of the RouterBOARD (`192.168.2.199`)

Now you can open a browser on your PC/phone and go to `http://192.168.4.1` (or the target's IP) to control the device directly!

---


## Verified Real-World Case Study: Tasmota AP Connection & Port Forwarding

An experimental Tasmota ESP8266 AP is currently used to test this configuration:
* **SSID**: `tasmota-C0AEC0-3776`
* **Subnet Target IP**: `192.168.4.1`

### Step-by-Step Configuration Applied:

1. **Station Link Configuration**:
   The RouterBOARD's wireless client `wlan1` is set to station mode and connected directly to `tasmota-C0AEC0-3776`. A static IP of `192.168.4.10/24` is bound to `wlan1` for instant reachability.

2. **Destination NAT (Dst-NAT) Port Forwarding**:
   To allow users on the home network (`192.168.2.x`) to access the Tasmota interface (port 80) without adding complex local static routes, we mapped the port of the remote device (adding a `1000` to port `80`) to the RouterBOARD:
   - **RouterBOARD Proxy Entry Point**: `192.168.2.199:1080`
   - **Tasmota Target Point**: `192.168.4.1:80`

3. **Active Verification**:
   Querying the RouterBOARD proxy port from any machine on the main network:
   ```bash
   curl -I http://192.168.2.199:1080
   ```
   Yields a successful proxy response:
   ```text
   HTTP/1.1 302 Found
   Content-Type: text/plain
   Location: http://192.168.4.1
   ...
   ```

---

## Command Line Discovery & Connection Utility

Instead of logging into WebFig manually every time you switch IoT devices, we will implement a command-line utility. 

### Planned Features:
1. **Scan**: Triggers a wireless scan on the RouterBOARD's `wlan1` interface to discover surrounding AP networks.
2. **List**: Shows the SSID, Signal Strength (RSSI), and encryption status of all discovered APs.
3. **Connect**: Prompts the user to choose an AP from the list (and enter a password if needed). It then configures the wireless profile and IP settings on the RouterBOARD automatically in seconds.
