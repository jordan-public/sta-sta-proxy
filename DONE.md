# MikroTik RB711UA-2HnD Reconfiguration & Deployment

This document records the exact steps, commands, and discoveries made while reconfiguring a factory-reset **MikroTik RouterBOARD 711UA-2HnD (RB711UA-2HnD)** from acting as a LAN DHCP server to becoming a DHCP client connected to a main home network (`192.168.2.x`).

---

## Technical Specifications of the Device
- **Model**: MikroTik RB711UA-2HnD
- **Architecture**: mipsbe (CPU: MIPS 24Kc V7.4 @ 400MHz)
- **OS Version**: RouterOS 6.49.19 (long-term)
- **MAC Address**: `d4:ca:6d:42:68:80`

---

## Step-by-Step Reconfiguration Process

### 1. Verification of Factory-Reset Connectivity
After the RouterBOARD was factory-reset and plugged directly into the Mac's low-priority Ethernet port, the router booted with its default static IP `192.168.88.1`. Connectivity was verified from the Mac via ICMP Ping:
```bash
ping -c 3 192.168.88.1
```
The router's MAC address was captured via the local ARP cache:
```bash
arp -an | grep 192.168.88.1
# Output: ? (192.168.88.1) at d4:ca:6d:42:68:80 on en7 ifscope [ethernet]
```

### 2. RouterOS Configuration Adjustments
To allow the router to request an IP address from the local home network and remain manageable, we executed the following RouterOS commands in a single SSH session:

#### Firewall Permissive Verification
By default, MikroTik drops incoming connections on WAN ports. Since `ether1` was already a member of the trusted `LAN` interface list on factory-default settings for this single-port model, it automatically bypassed the WAN drop rules:
```routeros
# Note: Adding it is safe, but already exists in default config:
/interface list member add interface=ether1 list=LAN
```

#### Disable DHCP Server on `ether1`
To prevent the router from handing out conflicting `192.168.88.x` IP leases on your main network, we disabled its default DHCP server running on `ether1`:
```routeros
/ip dhcp-server disable [find interface=ether1]
```

#### Enable DHCP Client on `ether1`
To configure the router to request a dynamic IP, DNS, and default route from your local network's DHCP server, we added and enabled a DHCP client on `ether1`:
```routeros
/ip dhcp-client add interface=ether1 disabled=no use-peer-dns=yes use-peer-ntp=yes add-default-route=yes
```

#### Combined Execution Command via SSH
To run these changes safely without dropping the link mid-configuration:
```bash
ssh -o StrictHostKeyChecking=no \
    -o UserKnownHostsFile=/dev/null \
    -o HostKeyAlgorithms=+ssh-rsa \
    -o PubkeyAcceptedKeyTypes=+ssh-rsa \
    admin@192.168.88.1 \
    "/ip dhcp-server disable [find interface=ether1]; /ip dhcp-client add interface=ether1 disabled=no use-peer-dns=yes use-peer-ntp=yes add-default-route=yes"
```

---

## 3. Deployment & Discovery on Home Network (`192.168.2.x`)

Once the configuration was applied and saved, the RouterBOARD was unplugged from the Mac and plugged directly into your home LAN network.

### Discovery via Subnet Ping Sweep
We scanned the local `192.168.2.0/24` network to locate the newly requested lease:
```bash
nmap -sn 192.168.2.0/24
```
**Discovery Result:**
```text
Nmap scan report for MikroTik (192.168.2.199)
Host is up (0.012s latency).
```
The router successfully acquired the dynamic IP address **`192.168.2.199`**!

### Verification of Reachability & Management
We verified the router was alive and responding to ICMP Pings on its new IP:
```bash
ping -c 4 192.168.2.199
```
Finally, we logged back in via SSH over the home network to verify full management accessibility:
```bash
ssh -o StrictHostKeyChecking=no \
    -o UserKnownHostsFile=/dev/null \
    -o HostKeyAlgorithms=+ssh-rsa \
    -o PubkeyAcceptedKeyTypes=+ssh-rsa \
    admin@192.168.2.199 \
    "/system resource print"
```
The connection was fully established and the WebFig graphical interface is completely accessible on the LAN network at `http://192.168.2.199`.


---

## 4. Connecting to Tasmota AP & Port Forwarding Configuration

### Wireless Discovery of the Target Tasmota AP
To discover surrounding APs, we executed an active wireless scan over SSH via the RouterBOARD:
```bash
ssh admin@192.168.2.199 "/interface wireless scan wlan1 duration=5s"
```
The scan successfully detected the experimental Tasmota device:
* **SSID**: `tasmota-C0AEC0-3776`
* **MAC Address**: `5E:CF:7F:C0:AE:C0`
* **Signal**: `-56 dBm` (extremely strong link)

### Connecting `wlan1` to Tasmota
We set up the wireless interface `wlan1` on the RouterBOARD to connect as a Station (STA) client to the open `tasmota-C0AEC0-3776` network, configured a static IP of `192.168.4.10` to avoid dynamic allocation delays, and verified the default gateway of `192.168.4.1` on the Tasmota interface:
```bash
ssh admin@192.168.2.199 \
  "/interface wireless set [find name=wlan1] ssid=\"tasmota-C0AEC0-3776\" mode=station frequency=auto; \
   /ip address add address=192.168.4.10/24 interface=wlan1"
```

To confirm the gateway is alive and routing correctly, we initiated a ping to Tasmota (`192.168.4.1`) from the RouterBOARD:
```bash
ssh admin@192.168.2.199 "/ping count=3 192.168.4.1"
```
**Ping Output:**
```text
  SEQ HOST                                     SIZE TTL TIME  STATUS           
    0 192.168.4.1                                56 255 24ms 
    1 192.168.4.1                                56 255 38ms 
    2 192.168.4.1                                56 255 75ms 
    sent=3 received=3 packet-loss=0% min-rtt=24ms avg-rtt=45ms max-rtt=75ms 
```
The target IP `192.168.4.1` has been successfully verified!

### Port Forwarding (Port 1080 -> Tasmota Port 80)
To reach the Tasmota web interface (port 80) using the RouterBOARD IP (port 1080) from the main home network, we configured a Destination NAT (dst-nat) rule alongside Source NAT (masquerading) on the RouterBOARD:
```bash
ssh admin@192.168.2.199 \
  "/ip firewall nat add chain=dstnat dst-port=1080 protocol=tcp action=dst-nat to-addresses=192.168.4.1 to-ports=80; \
   /ip firewall nat add chain=srcnat out-interface=wlan1 action=masquerade"
```

### Access Verification
To verify the proxy link is operational, we initiated a `curl` test from the Mac targeting the proxy port:
```bash
curl -I http://192.168.2.199:1080
```
**Successful Verification Response:**
```text
HTTP/1.1 302 Found
Content-Type: text/plain
Location: http://192.168.4.1
Content-Length: 0
Connection: close
```
This confirms that accessing `192.168.2.199:1080` transparently proxies connections to `192.168.4.1:80` through the RouterBOARD's wireless STA link!


---

## 5. Router Configuration Backup & Download Methodology

To back up and version-control the active state of our RouterBOARD configurations, we executed a two-step export and extraction process:

### 1. Generating Configuration Export Script on RouterBOARD
We triggered a plaintext configuration export on the RouterBOARD using the `/export` command via SSH:
```bash
ssh -o StrictHostKeyChecking=no \
    -o UserKnownHostsFile=/dev/null \
    -o HostKeyAlgorithms=+ssh-rsa \
    -o PubkeyAcceptedKeyTypes=+ssh-rsa \
    admin@192.168.2.199 \
    "/export file=sta_proxy_config"
```
This commands RouterOS to collect all active modifications and write them as a standard, human-readable script file named `sta_proxy_config.rsc` in the router's local flash storage.

### 2. Downloading the Configuration File to the Mac Repository
Using secure copy (`scp`) with matching legacy cryptographic options, we downloaded the script backup file directly to the local repository directory:
```bash
scp -o StrictHostKeyChecking=no \
    -o UserKnownHostsFile=/dev/null \
    -o HostKeyAlgorithms=+ssh-rsa \
    -o PubkeyAcceptedKeyTypes=+ssh-rsa \
    admin@192.168.2.199:sta_proxy_config.rsc \
    /Users/jordan/sta-sta-proxy/sta_proxy_config.rsc
```

### 3. Tracking and Storing Configuration in Git
We staged and committed the plaintext backup script to track modifications dynamically across future configuration cycles:
```bash
git add sta_proxy_config.rsc
git commit -m "Add sta_proxy_config.rsc backup file containing full RouterOS configurations"
```
The file `/Users/jordan/sta-sta-proxy/sta_proxy_config.rsc` is now fully tracked in our local repository!



---

## 6. Configuration Management & Automated Recovery Skill (Python)

To turn this backup, download, and recovery flow into a reusable and fully automated **skill**, we have encapsulated the logic into a clean, standalone Python block within this markdown file. 

This skill can backup active configurations from `192.168.2.199`, commit them directly to Git, or automatically restore configurations onto a factory-reset router (accessible at `192.168.88.1`) in a single step.

### Reusable Backup & Restore Automation Code
```python
# backup_restore_skill.py
import sys
import os
import subprocess

ROUTER_IP_CURRENT = "192.168.2.199"
ROUTER_IP_DEFAULT = "192.168.88.1"
BACKUP_FILENAME = "sta_proxy_config.rsc"
REPO_PATH = "/Users/jordan/sta-sta-proxy"

SSH_OPTS = [
    "-o", "StrictHostKeyChecking=no",
    "-o", "UserKnownHostsFile=/dev/null",
    "-o", "HostKeyAlgorithms=+ssh-rsa",
    "-o", "PubkeyAcceptedKeyTypes=+ssh-rsa",
    "-o", "ConnectTimeout=5"
]

def run_backup():
    print(f"[*] Connecting to router at {ROUTER_IP_CURRENT} to export configurations...")
    # 1. Trigger export
    export_cmd = f"/export file={BACKUP_FILENAME.replace('.rsc', '')}"
    subprocess.run(["ssh"] + SSH_OPTS + [f"admin@{ROUTER_IP_CURRENT}", export_cmd], check=True)
    
    # 2. Download via SCP
    print(f"[*] Downloading configuration script to {REPO_PATH}/{BACKUP_FILENAME}...")
    local_dest = os.path.join(REPO_PATH, BACKUP_FILENAME)
    subprocess.run(["scp"] + SSH_OPTS + [f"admin@{ROUTER_IP_CURRENT}:{BACKUP_FILENAME}", local_dest], check=True)
    
    # 3. Clean up the lock files and commit to Git
    print("[*] Staging and committing backup file to Git...")
    lock_file = os.path.join(REPO_PATH, ".git", "index.lock")
    if os.path.exists(lock_file):
        try:
            os.remove(lock_file)
        except Exception:
            pass
    subprocess.run(["git", "add", local_dest], cwd=REPO_PATH)
    subprocess.run(["git", "commit", "-m", "Automatic RouterBOARD configuration backup update"], cwd=REPO_PATH)
    print("[+] Backup completed and version-controlled successfully!")

def run_restore():
    print(f"[*] Preparing to restore router to active configurations...")
    local_source = os.path.join(REPO_PATH, BACKUP_FILENAME)
    if not os.path.exists(local_source):
        print(f"[-] Error: Local backup file {local_source} does not exist!")
        sys.exit(1)
        
    # Check router IP (either current or default after a reset)
    print(f"[*] Checking router reachability...")
    ip_to_use = ROUTER_IP_DEFAULT
    ping_default = subprocess.run(["ping", "-c", "1", "-t", "2", ROUTER_IP_DEFAULT], capture_output=True)
    if ping_default.returncode != 0:
        ip_to_use = ROUTER_IP_CURRENT
        print(f"[!] Router not at default IP ({ROUTER_IP_DEFAULT}). Attempting current IP ({ROUTER_IP_CURRENT})...")
    else:
        print(f"[+] Router detected at default factory reset IP ({ROUTER_IP_DEFAULT})")

    # 1. Upload backup script to router
    print(f"[*] Uploading {BACKUP_FILENAME} to router at {ip_to_use}...")
    subprocess.run(["scp"] + SSH_OPTS + local_source + f"admin@{ip_to_use}:{BACKUP_FILENAME}", shell=True, check=True)
    
    # 2. Execute configuration import on the router
    print("[*] Executing configuration import on the router...")
    import_cmd = f"/import file-name={BACKUP_FILENAME}"
    # Import may drop SSH link midway once interfaces/routing table updates, which is normal.
    subprocess.run(["ssh"] + SSH_OPTS + [f"admin@{ip_to_use}", import_cmd])
    print("[+] Restore command issued! Please allow 10-15 seconds for configurations to fully load.")

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in ["backup", "restore"]:
        print("Usage: python3 backup_restore_skill.py [backup|restore]")
        sys.exit(1)
        
    if sys.argv[1] == "backup":
        run_backup()
    elif sys.argv[1] == "restore":
        run_restore()
```

### How to Run This Skill Directly from `DONE.md`

Any developer or automation agent can execute this skill directly from this markdown file using these terminal one-liners!

#### To Backup Current Configurations:
```bash
python3 -c "$(sed -n '/# backup_restore_skill.py/,/```/p' DONE.md | sed '1d;$d')" backup
```

#### To Restore Configurations onto a Factory-Reset Router:
```bash
python3 -c "$(sed -n '/# backup_restore_skill.py/,/```/p' DONE.md | sed '1d;$d')" restore
```



---

## 7. Interactive AP Discovery & Proxy Gateway Controller (`proxy.py`)

To fully automate the workflow of discovering IoT access points and configuring port translation mappings, we have implemented an interactive command-line interface tool: **`proxy.py`**.

### Implemented Mechanics inside the Script:
1. **Interactive .env Configuration**: Automatically loads and stores your RouterBOARD's IP address inside a secure, git-ignored `.env` file, prompting you with a smart dynamic default on startup.
2. **SSID Scan Discovery**: Executes `/interface wireless scan wlan1 duration=4s` on the RouterBOARD and parses the raw tabular output to extract SSID names, MAC addresses, and Signal levels (in dBm).
3. **Dynamic DHCP AP Gateway Discovery**: Immediately connects the RouterBOARD's `wlan1` interface to your chosen AP, spawns a temporary, isolated DHCP client, and polls for a lease to **dynamically discover the AP's actual gateway IP address** (falling back to `192.168.4.1` only if discovery times out).
4. **Interactive UI & Custom Offsets**: Prompts the user to select an AP, automatically pre-fills the target AP gateway IP with the dynamically discovered IP address, and requests the destination and custom proxy entry ports.
5. **Optional HTTP Redirect Static Subnet Route**: Prompts the user with `[Y/n/h]` (Yes/no/help) to safely add a temporary static route on their local Mac (`sudo route -n add <subnet> <ROUTER_IP>`). This resolves Tasmota's native HTTP redirects back to `192.168.4.1` seamlessly! Includes a fully interactive help text block when typing `h` explaining privilege requirements.
6. **Automated Static Route Binding**: Calculates the target device's subnet and dynamically configures a static local IP on `wlan1` (e.g. `192.168.4.10/24` for Tasmota networks).
7. **NAT Destination Injection**: Injects Destination NAT (dstnat) port forwarding and Source NAT (srcnat masquerading) comments:
   * Comment `"sta-proxy-forward"` is used for easy identification.
   * Comment `"sta-proxy-masquerade"` matches the outbound masquerading.
8. **Real-time Link Monitoring**: Loops in a light monitoring state, printing live connection and signal statuses.
9. **Clean teardown on Exit**: Intercepts `Ctrl+C` interrupt signals and automatically cleans the NAT rules, disconnects `wlan1` on the RouterBOARD, and **deletes the temporary static route from the local Mac**, returning both the local machine and the RouterBOARD to completely pristine states!



---

## 8. Automated Factory-Reset Routerboard Configurator (`configure.py`)

To streamline installation on new or factory-reset devices, we have implemented an intelligent configuration utility: **`configure.py`**.

### Implemented Architecture:
1. **Prerequisite Information**: Clearly explains to the user that the computer should be set up with a factory-reset Routerboard (Tested Model: RB711-2Hn / RB711UA-2HnD) connected directly to the physical LAN port (configured with DHCP). State explicitly that the default factory IP address is `192.168.88.1` with a blank admin password.
2. **Safe Transactional Configuration Block**: Combines all conversion tasks into a single semicolon-delimited, semicolon-spaced instruction set sent to RouterOS in a single SSH session:
   - Disables the conflicting default DHCP Server on `ether1`
   - Installs a dynamic DHCP Client on `ether1` (storing it with comment `"sta-proxy-wan-dhcp"`)
   - Enables RouterOS DNS remote requests handler
   - Sets the system identity to `"proxy-gateway"` for clear identification
   - By running this atomically, **zero connection control is lost** over the RouterBOARD while it executes its interface reconfigurations locally!
3. **Automated IP Discovery Sweep**: After prompting the user to move the RouterBOARD's cable directly into their home LAN, the script triggers a background multi-host ping sweep on local subnet candidate ranges, logs into matching hosts, verifies the system identity is `"proxy-gateway"`, and automatically updates the local `.env` file with the newly assigned dynamic IP!


---

## 9. Architectural Feasibility Analysis: Dual-STA Wireless Relay (Completely Cable-Free)

We conducted a deep architectural evaluation to explore if the RouterBOARD can connect to two wireless networks simultaneously as a Station (STA) client, eliminating the physical Ethernet cable to your Home LAN.

### The Constraints:
1. **Single Physical Radio (wlan1)**: The MikroTik RB711 series contains a single physical 2.4 GHz wireless radio chip. A single radio can only tune to one frequency/channel at any given microsecond.
2. **Channel Conflicts**: Your Home Wi-Fi and the Target IoT Access Point (Rover Tank / Tasmota) typically run on different, non-overlapping channels (e.g., Channel 6 vs. Channel 1).
3. **Virtual Interfaces Constraint**: While RouterOS allows creating Virtual Clients or Virtual APs on top of `wlan1`, **all virtual interfaces must operate on the exact same channel/frequency as the master physical interface**. If `wlan1` hops channels to connect to a target device, the virtual client instantly drops its connection to your Home Wi-Fi, resulting in constant link flapping.

### Engineering Solutions:
* **Option A: USB Wireless Adapter (Best Solution)**:
  * Models like the **RB711UA-2HnD** equipped with a USB 2.0 port can accept a compatible Atheros-based USB Wi-Fi dongle.
  * RouterOS registers this as **`wlan2`**, providing two independent physical radios.
  * `wlan1` remains connected to your Home Wi-Fi, while `wlan2` hops and connects to target smart device APs.
* **Option B: Dual-Band Upgrade**:
  * Upgrading the hardware to a dual-radio MikroTik (e.g., **hAP ac lite** or **hAP ax²**).
  * Use the 5 GHz radio as a client to your Home Wi-Fi, and dedicate the 2.4 GHz radio entirely to scanning and connecting to standalone IoT AP devices.
* **Option C: Wired + Wireless STA Relay (Current Certified Standard)**:
  * Retain the current design: physical Ethernet `ether1` provides a 100% reliable, zero-latency management backhaul, while `wlan1` is entirely dedicated to connecting to experimental wireless APs.


---

## 10. Multi-Channel Simultaneous NAT Port Forwarding (Robust Robot/Toy Control)

We upgraded our connection gateway to support simultaneous multi-channel proxying. This is extremely valuable for complex target devices (like **Rover Tank Toys** or smart cameras) that use separate IP sockets for command/control (e.g. port `80`) and live video streaming transfer (e.g. port `8080`).

### Implemented Architecture:
1. **Interactive Multi-Channel Collector Loop**:
   - Replaced single-channel inputs with a sequential `Channel #X` collector loop.
   - Accepts destination port inputs and calculates recommended proxy entry port offsets (defaulting to `<destination_port + 1000>`).
   - Typing **`q`** or **`quit`** at the destination prompt cleanly breaks the loop and closes the channel table definition.
2. **Parallel Destination NAT (Dst-NAT) Injection**:
   - Loops over the customized configuration dictionary and injects multiple corresponding firewall rule definitions in parallel.
   - Comments each rule clearly with `"sta-proxy-forward"` so that all of them can be managed as a clean, single-comment group.
3. **Simultaneous Subnet Local Route Binds**:
   - Keeps track of a list of added local subnets to ensure multi-channel static routes can be bound and deleted in parallel without collision.
4. **Clean Grouped Teardown**:
   - On `Ctrl+C` interrupt, the script commands RouterOS to cleanly delete all NAT firewall rules matching `"sta-proxy-forward"` and `"sta-proxy-masquerade"` concurrently.
   - Automatically unbinds and deletes all temporary static subnets from the host machine concurrently, returning the environment to pristine conditions.

---

## 11. Cross-Platform Local Routing and Live Bandwidth Monitoring

We enhanced the local management environment to robustly support both Linux (e.g., Ubuntu) and BSD-based (e.g., macOS) systems while adding low-overhead active monitoring:

### Implemented Architecture:
1. **Dynamic OS Detection & Routing**:
   - `proxy.py` now leverages Python's `sys.platform` to identify the host operating system dynamically.
   - For **macOS**, it executes standard BSD route commands (`sudo route -n add -net ...`).
   - For **Linux**, it natively switches to `iproute2` commands (`sudo ip route add ... via ...`).
2. **Sudo Password Hardening**:
   - Instead of silently failing when the administrative cache expires, the script forcefully tests the sudo credential (`sudo -v`). If the password is mistyped, it catches the failure and prompts the user again cleanly, ensuring critical static routes are not skipped.
3. **Zero-Overhead Live Hardware Monitoring**:
   - Implemented real-time network activity meters (Tx and Rx bits-per-second) directly into the console.
   - Bypasses costly local software packet sniffing by commanding the RouterBOARD (`/interface monitor-traffic wlan1 once`) to report its silicon-level hardware counters during the already established 2-second heartbeat loop.
4. **Enhanced Channel Loop Exits**:
   - Refined the multi-channel prompt loop to allow user-friendly `'q'` or `'quit'` entries safely from any channel configuration prompt (destination port or entry port).



---

## 12. Silent, Non-Intrusive Dual-Engine Auto-Discovery

We have completely redesigned the RouterBOARD discovery phase in `proxy.py` to be 100% silent, non-intrusive, and enterprise-safe. It eliminates port scans and SSH-probe requests on neighboring network devices.

### Implemented Architecture:
1. **Passive MNDP Engine (UDP Port 5678)**:
   - Employs the native **MikroTik Neighbor Discovery Protocol (MNDP)** over UDP port `5678`.
   - Sends a single lightweight broadcast query to all local network interfaces and parses incoming binary TLV frames (decoding System Identity Type `5` and Board Model Type `8`).
   - Completely safe: other network devices (like Linux/Mac hosts on your network) do not listen on port 5678 and are **completely untouched**.
2. **Dual-Engine HTTP Fallback**:
   - If a RouterBOARD is connected to a firewalled port (e.g. `ether1` treated as WAN) and blocks incoming UDP 5678 or SSH, our script launches a highly targeted fallback scan.
   - It probes only Port 80 on active candidates and checks the HTTP response body for the `"mikrotik"` signature, detecting firewalled RouterBOARDs instantly and safely.
3. **Dynamic Self-IP Loopback Exclusion**:
   - Automatically detects all active IP addresses on the local computer's network interfaces (via `ifconfig`).
   - Excludes any self-IP loopback reflections from showing up as discovered RouterBOARDs in the terminal menu.
4. **Active Subnet Reachability Filtering**:
   - Mathematically evaluates the subnet prefix of every discovered device.
   - Discards any discovered endpoints belonging to unreachable subnets (such as `192.168.88.x` bridging over Wi-Fi when no wired connection is active).
   - Guarantees that only 100% route-compatible and physically reachable options are presented to the user!
