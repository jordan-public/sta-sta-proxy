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

