# sta-sta-proxy: Seamless IoT & Device Control Gateway

This project configures a **MikroTik RouterBOARD (RB711UA-2HnD)** to act as a wireless Station (STA) that connects to smart devices/appliances operating in Access Point (AP) mode (such as Tasmota plugs, Rover Tanks, or other IoT configuration portals). 

By connecting the RouterBOARD's physical `ether1` interface to your regular LAN, you can control and configure these standalone AP devices directly from any computer, tablet, or phone on your primary network. You never have to disconnect from your home network or switch WiFi SSIDs again!

---

## The Core Concept: Layer 3 STA Proxy Gateway

```text
                     --- SYSTEM ARCHITECTURE DIAGRAM ---

  [ Computer / Phone ] (e.g., IP: 192.168.2.50)
         │
         │ (HTTP Access to Proxy, e.g. http://192.168.2.199:1080)
         ▼
  ┌────────────────────────────────────────────────────────┐
  │              YOUR MAIN HOME LAN (192.168.2.x)          │
  └───────────────────────────┬────────────────────────────┘
                              │
                              │ (Physical RJ45 Ethernet Cable)
                              ▼
  ┌────────────────────────────────────────────────────────┐
  │            STA PROXY GATEWAY (MikroTik RB711)          │
  │                                                        │
  │  - ether1 Port IP: 192.168.2.199 (From Home DHCP)      │
  │  - wlan1 Wireless: 192.168.4.10  (Static IP on AP)     │
  │                                                        │
  │  - NAT Forwarding: Dst-NAT 1080 -> 192.168.4.1:80      │
  │  - Masquerade NAT: Src-NAT out-interface=wlan1         │
  └───────────────────────────┬────────────────────────────┘
                              │
                              │ (Wireless Connection Link)
                              ▼
                      )))  Wireless  (((
                              │
                              ▼
  ┌────────────────────────────────────────────────────────┐
  │       TARGET AP DEVICE (e.g., Rover Tank Toy AP)       │
  │                                                        │
  │  - Hosts autonomous WiFi AP: "Rover-Tank-XXXX"         │
  │  - Native Gateway IP: 192.168.4.1                      │
  │  - Local Device Port: 80                               │
  └────────────────────────────────────────────────────────┘
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

## Automated Factory-Reset RouterBOARD Configuration

If you have a fresh, factory-reset RouterBOARD (or a device that automatically resets to factory settings on reboot), you can completely configure it as our L3 STA Proxy Gateway automatically in one step!

### How to use the Configurator:

1. **Connect the RouterBOARD**:
   - Plug the RouterBOARD's LAN port directly into your computer's Ethernet port.
   - Set your Mac's Ethernet port configuration to **DHCP** so it receives an IP address (typically `192.168.88.x`).
   - The default factory IP of the RouterBOARD is **`192.168.88.1`** (blank admin password).

2. **Run the Configurator**:
   ```bash
   python3 configure.py
   ```
   
3. **Pristine Reconfiguration Sequence (No-Disconnection Guarantee)**:
   - The tool automatically verifies reachability and deploys a single transactional atomic configuration block via SSH.
   - It disables the RouterBOARD's LAN DHCP Server, registers a safe home network DHCP Client, enables remote DNS requests, and renames the system identity to `proxy-gateway`.
   - Running this atomically ensures **zero control loss** over the router during its interface reconfigurations!

4. **Network Relocation & Auto-Discovery Sweep**:
   - The script prompts you to move the RouterBOARD's Ethernet plug directly into your active home network router/switch.
   - It immediately runs a fast multi-host background discovery ping sweep to pinpoint the RouterBOARD's new IP address, verify its identity, and write it directly into your local `.env` file!

---

## Command Line Discovery & Connection Utility

Instead of logging into WebFig manually every time you switch IoT target devices, we have implemented an interactive command-line controller: **`proxy.py`**.

The utility communicates directly with the RouterBOARD over SSH to orchestrate active wireless scans, select AP targets, auto-configure Layer 3 IP bindings, set up custom port translation offset mappings, and monitor the live connection.

### Environment Configuration (`.env`)

Before running the utility, copy the example environment file and set your RouterBOARD's IP address:
```bash
cp .env.example .env
```
Open `.env` and configure your RouterBOARD's active IP address:
```env
ROUTER_IP=192.168.2.199
```
*(This IP address is securely stored locally and is ignored by Git, keeping your environment portable!)*

### How to Use the Connection Utility:

1. **Run the utility** from the repository directory:
   ```bash
   python3 proxy.py
   ```

2. **Scan and Select**:
   The script triggers a 4-second active scan on the RouterBOARD and prints a sorted table of all discovered APs:
   ```text
   ============================================================
    sta-proxy-cli: RouterBOARD IoT Proxy Connection Manager
   ============================================================
   [*] Scanning for wireless Access Points on 192.168.2.199...
   
   Available WiFi Access Points:
   #    SSID                           MAC Address          Signal    
   --------------------------------------------------------------------
   1    tasmota-C0AEC0-3776            5E:CF:7F:C0:AE:C0    -56 dBm
   2    jordan                         3C:F0:83:1C:92:95    -30 dBm
   3    Chesaco                        04:70:56:57:9C:28    -64 dBm
   
   Select target network (1-3): 1
   ```

3. **Dynamic AP Gateway Discovery & Port Selection**:
   - **Connection & DHCP Discovery**: The script immediately connects `wlan1` to your selected AP and spawns a temporary, isolated DHCP client to **dynamically discover the AP's actual gateway IP address**!
   - **Destination Port**: Enter the port of the target smart device (default: `80` in brackets).
   - **Proxy Port**: Enter the entrance port of the proxy on the RouterBOARD (default: `<destination_port + 1000>` in brackets).
   - **Gateway IP**: Choose the target AP gateway IP address. The default in brackets is the **dynamically discovered IP** (falling back to `192.168.4.1` only if discovery times out!).
   ```text
   [*] Connecting wlan1 to SSID "tasmota-C0AEC0-3776"...
   [*] Spawning temporary DHCP client on wlan1 to discover gateway IP...
   [+] Dynamically discovered AP gateway IP: 192.168.4.1
   
   Enter destination port (default: 80): 
   Enter proxy port (default: 1080): 
   Enter target AP gateway IP (default: 192.168.4.1): 
   ```

4. **Live Proxy Mapping**:
   The script dynamically creates the NAT tables and goes into a real-time monitor loop, outputting the wireless link signal:
   ```text
   ============================================================
    [+] PROXY GATEWAY IS LIVE AND ACTIVE!
        Access in your web browser: http://192.168.2.199:1080
   ============================================================
   Press Ctrl+C to disconnect and stop the proxy.
   [03:40:12] Link Status: Active | Signal: -56dBm
   ```

5. **Clean Termination**:
   Simply hit **`Ctrl+C`**. The script immediately intercepts the interrupt and commands the RouterBOARD to cleanly tear down the forwarding tables, erase custom NAT mappings, and disconnect `wlan1` to preserve pristine router performance:
   ```text
   ^C
   [!] Interrupt received.
   
   [*] Cleaning up RouterBOARD proxy rules...
   [+] RouterBOARD rules cleaned up successfully.
   
   [+] Exited cleanly. Goodbye!
   ```

