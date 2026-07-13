#!/usr/bin/env python3
"""
sta-proxy-cli: Interactive AP Discovery & RouterBOARD Multi-Channel Proxy Gateway Controller
"""

import sys
import os
import subprocess
import re
import time
import socket

def load_dotenv():
    """Parse local .env file key-values into os.environ if it exists."""
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, val = line.split("=", 1)
                    os.environ[key.strip()] = val.strip()

def save_dotenv(router_ip):
    """Save ROUTER_IP into .env file permanently."""
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    with open(env_path, "w") as f:
        f.write(f"# Local Environment Configurations\nROUTER_IP={router_ip}\n")

ROUTER_IP = None
SSH_OPTS = [
    "-o", "StrictHostKeyChecking=no",
    "-o", "UserKnownHostsFile=/dev/null",
    "-o", "HostKeyAlgorithms=+ssh-rsa",
    "-o", "PubkeyAcceptedKeyTypes=+ssh-rsa",
    "-o", "ConnectTimeout=5",
    "-o", "BatchMode=yes",
    "-o", "LogLevel=ERROR"
]

def run_ssh_cmd(cmd):
    """Run a command on the RouterBOARD via SSH and return output."""
    full_cmd = ["ssh"] + SSH_OPTS + [f"admin@{ROUTER_IP}", cmd]
    res = subprocess.run(full_cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"RouterBOARD SSH command failed: {res.stderr.strip()}")
    return res.stdout

# Static Routes tracking for multiple subnets
ADDED_ROUTES = [] # List of added subnets

def add_local_route(subnet_prefix, router_ip):
    """Add a static route on the local computer to access the target AP directly."""
    global ADDED_ROUTES
    subnet = f"{subnet_prefix}.0/24"
    
    # Avoid duplicate routes
    if subnet in ADDED_ROUTES:
        return

    is_mac = sys.platform == 'darwin'
    is_linux = sys.platform.startswith('linux')
    os_name = "Mac" if is_mac else ("Linux" if is_linux else "machine")
    
    route_cmd_example = f"sudo route -n add -net {subnet} {router_ip}" if is_mac else (f"sudo ip route add {subnet} via {router_ip}" if is_linux else "route add ...")

    help_text = (
        "\n--- Static Subnet Routing Help ---\n"
        "Some devices (like Tasmota) send an HTTP redirect to their native IP (e.g. 192.168.4.1) on login.\n"
        "If you do not route traffic, your web browser will try to reach 192.168.4.1 directly over your WiFi\n"
        "network instead of the RouterBOARD, causing connection timeouts.\n\n"
        "Modifying the routing table of your computer is a privileged system operation, so your administrator\n"
        "password may be prompted by 'sudo'.\n\n"
        "Don't worry, upon exit the added route will be automatically removed from your computer, leaving\n"
        "your system clean and unmodified.\n\n"
        f"By choosing [Y], we add a temporary routing rule to your {os_name}:\n"
        f"  {route_cmd_example}\n"
        "This routes all 192.168.4.x traffic through the RouterBOARD so redirects and web pages load perfectly!\n"
        "----------------------------------\n"
    )
    
    while True:
        choice = input(f"\nDo you want to configure a temporary routing rule to resolve HTTP redirects on {subnet}? [Y/n/h] (default: Y): ").strip().lower()
        if not choice:
            choice = "y"
            
        if choice == "h":
            print(help_text)
            continue
        elif choice == "n":
            print("[*] Skipping automatic static route configuration.")
            return
        elif choice == "y":
            break
        else:
            print("[-] Invalid input. Please enter 'y', 'n', or 'h'.")

    print(f"\n[*] Configuring static routing rule on your {os_name}...")
    print(f"    Subnet: {subnet} -> Gateway: {router_ip}")
    print("[!] Admin password may be prompted by 'sudo' to update routing tables.")
    
    # Verify sudo password upfront
    while True:
        res = subprocess.run(["sudo", "-v"])
        if res.returncode == 0:
            break
        else:
            print("[-] wrong password. Please try again.")

    # Check if a route already exists and delete it first to prevent duplicates
    if is_mac:
        subprocess.run(["sudo", "route", "-n", "delete", "-net", subnet], capture_output=True)
        cmd = ["sudo", "route", "-n", "add", "-net", subnet, router_ip]
    elif is_linux:
        subprocess.run(["sudo", "ip", "route", "del", subnet], capture_output=True)
        cmd = ["sudo", "ip", "route", "add", subnet, "via", router_ip]
    else:
        print(f"[-] Unsupported OS '{sys.platform}' for automatic routing. Please configure manually.")
        return
    
    res = subprocess.run(cmd)
    if res.returncode == 0:
        if subnet not in ADDED_ROUTES:
            ADDED_ROUTES.append(subnet)
        print(f"[+] Local route added successfully: {subnet} -> {router_ip}")
    else:
        print("[-] Failed to configure local static route. You can configure it manually using:")
        print(f"    {route_cmd_example}")

def remove_local_routes():
    """Clean up all the local computer static routes."""
    global ADDED_ROUTES
    is_mac = sys.platform == 'darwin'
    is_linux = sys.platform.startswith('linux')
    os_name = "Mac" if is_mac else ("Linux" if is_linux else "machine")

    for subnet in ADDED_ROUTES:
        print(f"[*] Restoring your {os_name}'s routing table (deleting {subnet})...")
        if is_mac:
            cmd = ["sudo", "route", "-n", "delete", "-net", subnet]
        elif is_linux:
            cmd = ["sudo", "ip", "route", "del", subnet]
        else:
            continue
            
        res = subprocess.run(cmd, capture_output=True)
        if res.returncode == 0:
            print(f"[+] {os_name} routing table restored successfully for {subnet}.")
    ADDED_ROUTES = []

def clean_routerboard_rules():
    """Clean up any custom NAT rules, wlan1 configurations, and local routes."""
    # 1. Clean up local static routes
    remove_local_routes()
    
    # 2. Clean up RouterBOARD configurations
    print("\n[*] Cleaning up RouterBOARD proxy rules...")
    try:
        # Remove any NAT rules that use dst-port matching our forwarded port or masquerade on wlan1
        run_ssh_cmd("/ip firewall nat remove [find comment=\"sta-proxy-forward\"]")
        run_ssh_cmd("/ip firewall nat remove [find comment=\"sta-proxy-masquerade\"]")
        # Disconnect wlan1
        run_ssh_cmd("/interface wireless set [find name=wlan1] ssid=\"\"")
        print("[+] RouterBOARD rules cleaned up successfully.")
    except Exception as e:
        print(f"[-] Cleanup warning: {e}")

def parse_scan_output(output):
    """Parse the raw scan output from `/interface wireless scan`."""
    networks = []
    lines = output.strip().split("\n")
    seen_macs = set()
    for line in lines:
        line = line.strip()
        if not line or "ADDRESS" in line or "Flags:" in line:
            continue
        match = re.search(r"([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})", line)
        if match:
            mac = match.group(0)
            if mac in seen_macs:
                continue
            seen_macs.add(mac)
            
            parts = line.split(mac)
            if len(parts) > 1:
                right_side = parts[1].strip()
                sig_match = re.search(r"-\\d+", right_side)
                sig = sig_match.group(0) if sig_match else "unknown"
                
                freq_match = re.search(r"\d{4}/", right_side)
                if freq_match:
                    ssid = right_side.split(freq_match.group(0))[0].strip()
                else:
                    ssid = right_side.split(sig)[0].strip()
                
                if not ssid:
                    ssid = "<Hidden SSID>"
                
                # Smart Auto-Expansion for known abbreviated SSIDs
                if "..." in ssid:
                    mac_clean = mac.replace(":", "").replace("-", "").upper()
                    mac_last_6 = mac_clean[-6:]
                    if "tasmota" in ssid.lower():
                        ssid = f"tasmota-{mac_last_6}-3776"
                    else:
                        # Map common truncated local networks to their full names
                        known_expansions = {
                            "natural": "Natural Wireless",
                            "employee": "Employee",
                            "spectrum": "SpectrumWiFi",
                            "nw_hp203": "nw_hp2035",
                            "chesaco-": "Chesaco-Guest",
                            "verizon_": "Verizon_WiFi",
                            "jordan-g": "jordan-guest"
                        }
                        prefix = ssid.replace("...", "").lower()
                        for k, v in known_expansions.items():
                            if prefix.startswith(k) or k.startswith(prefix):
                                ssid = v
                                break
                
                networks.append({
                    "mac": mac,
                    "ssid": ssid,
                    "signal": sig
                })
    return networks


def discover_routerboards():
    """
    Discover all MikroTik Routerboards on the local network using a combination of:
    1. Active subnet scanning on SSH (Port 22).
    2. Active MNDP queries on UDP Port 5678.
    Returns a list of dicts: [{'name': name, 'ip': ip, 'model': model}]
    """
    import socket
    import struct
    import concurrent.futures
    import re

    print("[*] Performing plug-and-play auto-discovery for RouterBOARD devices...")
    discovered = {}

    # Gather local broadcast addresses and subnets
    broadcasts = []
    subnets = []
    try:
        out = subprocess.check_output(["ifconfig"], text=True)
        # Find all broadcasts
        broadcasts = list(set(re.findall(r"broadcast\s+([0-9.]+)", out)))
        # Find active local IPs to calculate subnets
        inet_ips = re.findall(r"inet\s+([0-9.]+)", out)
        for ip in inet_ips:
            if ip.startswith("127."):
                continue
            prefix = ".".join(ip.split(".")[:3])
            if prefix not in subnets:
                subnets.append(prefix)
    except Exception:
        pass

    # Standard candidate subnets
    if "192.168.2" not in subnets:
        subnets.append("192.168.2")
    if "192.168.88" not in subnets:
        subnets.append("192.168.88")

    # Compile candidate list (standard defaults + active subnets)
    candidates = ["192.168.88.1", "192.168.2.199"]
    for prefix in subnets:
        for host in range(1, 255):
            candidates.append(f"{prefix}.{host}")
    candidates = list(dict.fromkeys(candidates))

    # Standard SSH probe config
    ssh_opts = [
        "-o", "StrictHostKeyChecking=no",
        "-o", "UserKnownHostsFile=/dev/null",
        "-o", "HostKeyAlgorithms=+ssh-rsa",
        "-o", "PubkeyAcceptedKeyTypes=+ssh-rsa",
        "-o", "ConnectTimeout=4",
    "-o", "BatchMode=yes",
    "-o", "LogLevel=ERROR"
    ]

    def probe_ssh_host(ip):
        # Quick check if SSH port 22 is open first
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(0.5)
        try:
            s.connect((ip, 22))
            s.close()
        except Exception:
            return None

        # SSH port open! Fetch identity details
        try:
            cmd = ["ssh"] + ssh_opts + [f"admin@{ip}", ":put [/system identity get name]; :put [/system resource get board-name]"]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=4)
            if res.returncode == 0:
                lines = [line.strip() for line in res.stdout.split("\n") if line.strip()]
                if len(lines) >= 2:
                    name = lines[0]
                    model = lines[1]
                    return {"ip": ip, "name": name, "model": model}
        except Exception:
            pass
        return None

    # Probe candidates in parallel
    with concurrent.futures.ThreadPoolExecutor(max_workers=50) as executor:
        results = executor.map(probe_ssh_host, candidates)
        for r in results:
            if r:
                discovered[r["ip"]] = r

    return list(discovered.values())


def main():
    global ROUTER_IP
    print("=" * 60)
    print(" sta-proxy-cli: RouterBOARD Multi-Channel Proxy Gateway")
    print("=" * 60)
    
    # Load environment variables from local .env if present
    load_dotenv()
    
    default_ip = os.environ.get("ROUTER_IP", "").strip()
    
    # Run Auto-Discovery Sweep
    discovered = discover_routerboards()
    
    if discovered:
        print("\nDiscovered RouterBOARD Devices:")
        for idx, router in enumerate(discovered):
            print(f"  {idx + 1}) {router['name']} ({router['ip']}) - Model: {router['model']}")
        print("  Other) Enter custom IP address manually")
        
        while True:
            choice = input(f"\nSelect RouterBOARD (1-{len(discovered)}) or enter custom IP address: ").strip()
            if not choice:
                if default_ip:
                    ROUTER_IP = default_ip
                    break
                else:
                    print("[-] Please enter a valid selection or IP address.")
                    continue
            
            # Check if user entered a custom IP address
            if re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$", choice):
                ROUTER_IP = choice
                save_dotenv(ROUTER_IP)
                break
                
            try:
                sel_idx = int(choice) - 1
                if 0 <= sel_idx < len(discovered):
                    ROUTER_IP = discovered[sel_idx]["ip"]
                    save_dotenv(ROUTER_IP)
                    break
                else:
                    print(f"[-] Invalid selection. Enter 1-{len(discovered)} or a valid IP address.")
            except ValueError:
                # Treat other string inputs (hostname, etc.) as raw address
                ROUTER_IP = choice
                save_dotenv(ROUTER_IP)
                break
    else:
        print("\n[-] No RouterBOARD devices discovered automatically.")
        # Prompt the user for the RouterBOARD IP address
        if default_ip:
            user_ip = input(f"Enter RouterBOARD IP address (default: {default_ip}): ").strip()
            if not user_ip:
                ROUTER_IP = default_ip
            else:
                ROUTER_IP = user_ip
                save_dotenv(ROUTER_IP)
        else:
            while True:
                ROUTER_IP = input("Enter RouterBOARD IP address: ").strip()
                if ROUTER_IP:
                    save_dotenv(ROUTER_IP)
                    break
                print("[-] RouterBOARD IP is required to connect.")
        
    print(f"[*] RouterBOARD set to: {ROUTER_IP}")
    
    # 1. Scan for APs
    print(f"[*] Scanning for wireless Access Points on {ROUTER_IP}...\")")
    try:
        raw_scan = run_ssh_cmd("/interface wireless scan wlan1 duration=4s")
    except Exception as e:
        print(f"[-] Error: Could not connect or initiate scan on the RouterBOARD: {e}")
        sys.exit(1)
        
    networks = parse_scan_output(raw_scan)
    if not networks:
        print("[-] No networks discovered. Ensure the RouterBOARD wireless card is operational.")
        sys.exit(0)
        
    print("\nAvailable WiFi Access Points:")
    print(f"{'#':<4} {'SSID':<30} {'MAC Address':<20} {'Signal':<10}")
    print("-" * 68)
    for idx, net in enumerate(networks):
        print(f"{idx + 1:<4} {net['ssid']:<30} {net['mac']:<20} {net['signal']} dBm")
        
    # 2. Let User Choose
    while True:
        try:
            choice = input(f"\nSelect target network (1-{len(networks)}): ").strip()
            choice_idx = int(choice) - 1
            if 0 <= choice_idx < len(networks):
                selected_net = networks[choice_idx]
                break
            print("[-] Invalid selection. Enter a number within the range.")
        except ValueError:
            print("[-] Please enter a valid integer.")
            
    ssid_to_use = selected_net['ssid']
    if "..." in ssid_to_use:
        print(f"\n[!] Note: The SSID was abbreviated by the RouterBOARD as '{ssid_to_use}' due to terminal width.")
        # Calculate a smart default suggestion for Tasmota if possible
        mac_clean = selected_net['mac'].replace(":", "").replace("-", "").upper()
        mac_last_6 = mac_clean[-6:]
        default_suggestion = f"tasmota-{mac_last_6}-3776"
        user_ssid = input(f"Please enter the FULL unabbreviated SSID (default: {default_suggestion}): ").strip()
        if user_ssid:
            ssid_to_use = user_ssid
        else:
            ssid_to_use = default_suggestion
            
    print(f"\n[+] Selected AP SSID: {ssid_to_use} ({selected_net['mac']})")
    
    # 3. Configure Multi-Port Forwarding Loops
    port_configs = []
    print("\n--- MULTI-CHANNEL PROXY PORT CONFIGURATION ---")
    print("Enter the channels you wish to proxy (e.g. Port 80 for Control, Port 8080 for Video).")
    print("Type 'q' or 'quit' at the destination port prompt once you have finished adding channels.")
    
    channel_idx = 1
    while True:
        default_dest = 80 if channel_idx == 1 else 'q'
        
        target_port_str = input(f"\n[Channel #{channel_idx}] Enter destination port (default: {default_dest}, or 'q' to finish): ").strip().lower()
        
        if not target_port_str:
            target_port_str = str(default_dest)

        if target_port_str in ['q', 'quit']:
            if not port_configs:
                print("[-] You must configure at least one channel to start proxy.")
                continue
            break
            
        try:
            target_port = int(target_port_str)
            if not (0 < target_port <= 65535):
                print("[-] Invalid range. Enter a valid port (1-65535).")
                continue
        except ValueError:
            print("[-] Please enter a valid integer or 'q' to finish.")
            continue
                
        # Ask for corresponding proxy entry port (default destination + 1000)
        default_proxy = target_port + 1000
        abort_channel = False
        while True:
            forwarded_port_str = input(f"[Channel #{channel_idx}] Enter proxy entry port (default: {default_proxy}, or 'q' to finish): ").strip().lower()
            if not forwarded_port_str:
                forwarded_port = default_proxy
                break
            if forwarded_port_str in ['q', 'quit']:
                abort_channel = True
                break
            try:
                forwarded_port = int(forwarded_port_str)
                if 0 < forwarded_port <= 65535:
                    break
                print("[-] Invalid range. Enter a valid port (1-65535).")
            except ValueError:
                print("[-] Please enter a valid integer or 'q' to finish.")
                
        if abort_channel:
            if not port_configs:
                print("[-] You must configure at least one channel to start proxy.")
                continue
            break

        port_configs.append({
            'target_port': target_port,
            'forwarded_port': forwarded_port
        })
        print(f"[+] Added Channel #{channel_idx}: Proxy :{forwarded_port} -> Device :{target_port}")
        channel_idx += 1

    # Connect to Selected SSID immediately to run DHCP discovery
    print(f"\n[*] Connecting wlan1 to SSID \"{ssid_to_use}\"... ")
    try:
        run_ssh_cmd(f"/interface wireless set [find name=wlan1] ssid=\"{ssid_to_use}\" mode=station frequency=auto")
    except Exception as e:
        print(f"[-] Connection error: {e}")
        sys.exit(1)

    # Discover AP Gateway IP via temporary DHCP Client
    print("[*] Spawning temporary DHCP client on wlan1 to discover gateway IP...")
    target_ap_ip = "192.168.4.1" # default fallback
    try:
        # Pre-clean any old temp clients
        run_ssh_cmd("/ip dhcp-client remove [find comment=\"sta-proxy-temp-dhcp\"]")
        # Add new temp DHCP client
        run_ssh_cmd("/ip dhcp-client add interface=wlan1 disabled=no add-default-route=no comment=\"sta-proxy-temp-dhcp\"")
        
        # Poll for lease (up to 6 seconds)
        discovered = False
        for _ in range(6):
            time.sleep(1)
            dhcp_status = run_ssh_cmd("/ip dhcp-client print detail where comment=\"sta-proxy-temp-dhcp\"")
            if "gateway=" in dhcp_status:
                # Parse gateway IP
                gw_match = re.search(r"gateway=([0-9.]+)", dhcp_status)
                if gw_match:
                    target_ap_ip = gw_match.group(1)
                    print(f"[+] Dynamically discovered AP gateway IP: {target_ap_ip}")
                    discovered = True
                    break
            elif "dhcp-server=" in dhcp_status:
                # Parse dhcp-server IP
                srv_match = re.search(r"dhcp-server=([0-9.]+)", dhcp_status)
                if srv_match:
                    target_ap_ip = srv_match.group(1)
                    print(f"[+] Dynamically discovered AP gateway IP: {target_ap_ip}")
                    discovered = True
                    break
        if not discovered:
            print(f"[-] DHCP lease discovery timed out. Falling back to default: {target_ap_ip}")
    except Exception as e:
        print(f"[-] DHCP client discovery error: {e}. Falling back to default: {target_ap_ip}")
    finally:
        # Clean up the temporary DHCP client immediately so it does not interfere
        try:
            run_ssh_cmd("/ip dhcp-client remove [find comment=\"sta-proxy-temp-dhcp\"]")
        except Exception:
            pass

    # Prompt for Target AP IP overrides
    ip_override = input(f"Enter target AP gateway IP (default: {target_ap_ip}): ").strip()
    if ip_override:
        target_ap_ip = ip_override
        
    print(f"\n[*] Multi-Channel Proxy configuration summary:")
    for idx, cfg in enumerate(port_configs):
        print(f"    - Channel #{idx+1}: Entry Point http://{ROUTER_IP}:{cfg['forwarded_port']} -> Device http://{target_ap_ip}:{cfg['target_port']}")
    
    # 4. Apply Configurations to the RouterBOARD
    print("\n[*] Applying proxy gateway rules to the RouterBOARD...")
    try:
        # Pre-clean existing rules
        run_ssh_cmd("/ip firewall nat remove [find comment=\"sta-proxy-forward\"]")
        run_ssh_cmd("/ip firewall nat remove [find comment=\"sta-proxy-masquerade\"]")
        
        # Connect to Selected SSID
        print(f"[*] Connecting wlan1 to SSID \"{selected_net['ssid']}\"... ")
        run_ssh_cmd(f"/interface wireless set [find name=wlan1] ssid=\"{selected_net['ssid']}\" mode=station frequency=auto")
        
        # Configure Static IP for local subnet (assuming target_ap_ip is on a /24 subnet, let's use .10)
        subnet_prefix = ".".join(target_ap_ip.split(".")[:3])
        static_client_ip = f"{subnet_prefix}.10"
        print(f"[*] Assigning static IP {static_client_ip}/24 to wlan1...")
        # Remove any existing static IPs on wlan1 in that subnet first to avoid duplicate errors
        run_ssh_cmd(f"/ip address remove [find interface=wlan1 and address=\"{static_client_ip}/24\"]")
        run_ssh_cmd(f"/ip address add address={static_client_ip}/24 interface=wlan1")
        
        # Add dynamic local static route if user selected [Y] at the prompt
        add_local_route(subnet_prefix, ROUTER_IP)
        
        # Configure NAT Port Forwarding Rules for all requested channels
        for idx, cfg in enumerate(port_configs):
            print(f"[*] Creating dstnat port-forwarding rule #{idx+1} ({ROUTER_IP}:{cfg['forwarded_port']} -> {target_ap_ip}:{cfg['target_port']})... ")
            run_ssh_cmd(f"/ip firewall nat add chain=dstnat dst-port={cfg['forwarded_port']} protocol=tcp action=dst-nat to-addresses={target_ap_ip} to-ports={cfg['target_port']} comment=\"sta-proxy-forward\"")
        
        # Add outbound masquerading NAT
        run_ssh_cmd("/ip firewall nat add chain=srcnat out-interface=wlan1 action=masquerade comment=\"sta-proxy-masquerade\"")
        
    except Exception as e:
        print(f"[-] Configuration error: {e}")
        clean_routerboard_rules()
        sys.exit(1)
        
    # 5. Monitoring Loop
    print("\n" + "=" * 60)
    print(f" [+] MULTI-CHANNEL PROXY GATEWAY IS LIVE AND ACTIVE!")
    for idx, cfg in enumerate(port_configs):
        print(f"     - Channel #{idx+1}: http://{ROUTER_IP}:{cfg['forwarded_port']} (Forwarding to port {cfg['target_port']})")
    print("=" * 60)
    print("Press Ctrl+C to disconnect and stop the proxy.")
    
    try:
        while True:
            # Monitor wireless link status periodically
            try:
                reg_table = run_ssh_cmd("/interface wireless registration-table print; /interface monitor-traffic wlan1 once")
                if selected_net['mac'].lower() in reg_table.lower():
                    # Extract active signal strength
                    sig_match = re.search(r"-\d+dBm", reg_table)
                    sig_str = sig_match.group(0) if sig_match else "connected"
                    
                    # Extract Tx/Rx rates
                    tx_match = re.search(r"tx-bits-per-second:\s*([0-9\.]+[a-zA-Z]+)", reg_table)
                    rx_match = re.search(r"rx-bits-per-second:\s*([0-9\.]+[a-zA-Z]+)", reg_table)
                    tx_str = tx_match.group(1) if tx_match else "0bps"
                    rx_str = rx_match.group(1) if rx_match else "0bps"
                    
                    status_line = f"[{time.strftime('%H:%M:%S')}] Link: Active | Signal: {sig_str} | Tx: {tx_str} | Rx: {rx_str}"
                    print(f"{status_line:<75}", end="\r")
                else:
                    print(f"[{time.strftime('%H:%M:%S')}] Link Status: Connecting / Searching...{' ':20}", end="\r")
            except Exception:
                pass
            time.sleep(2)
    except KeyboardInterrupt:
        print("\n[!] Interrupt received.")
    finally:
        clean_routerboard_rules()
        print("\n[+] Stopped proxy controller cleanly. Goodbye!")

if __name__ == '__main__':
    main()
