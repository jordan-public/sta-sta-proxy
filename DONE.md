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
