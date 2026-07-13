#!/usr/bin/env python3
"""
sta-proxy-cli: Interactive AP Discovery & RouterBOARD Proxy Gateway Controller
"""

import sys
import os
import subprocess
import re
import time
import socket

ROUTER_IP = None
SSH_OPTS = [
    "-o", "StrictHostKeyChecking=no",
    "-o", "UserKnownHostsFile=/dev/null",
    "-o", "HostKeyAlgorithms=+ssh-rsa",
    "-o", "PubkeyAcceptedKeyTypes=+ssh-rsa",
    "-o", "ConnectTimeout=5"
]

def run_ssh_cmd(cmd):
    """Run a command on the RouterBOARD via SSH and return output."""
    full_cmd = ["ssh"] + SSH_OPTS + [f"admin@{ROUTER_IP}", cmd]
    res = subprocess.run(full_cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"RouterBOARD SSH command failed: {res.stderr.strip()}")
    return res.stdout

def clean_routerboard_rules():
    """Clean up any custom NAT rules and wlan1 configurations."""
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
                sig_match = re.search(r"-\d+", right_side)
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


def main():
    global ROUTER_IP
    print("=" * 60)
    print(" sta-proxy-cli: RouterBOARD IoT Proxy Connection Manager")
    print("=" * 60)
    
    # Determine default Router IP by quick ping check
    default_ip = "192.168.2.199"
    for cand in ["192.168.2.199", "192.168.88.1"]:
        res = subprocess.run(["ping", "-c", "1", "-t", "1", cand], capture_output=True)
        if res.returncode == 0:
            default_ip = cand
            break
            
    # Ask user for active RouterBOARD IP address
    user_ip = input(f"Enter RouterBOARD IP address (default: {default_ip}): ").strip()
    if user_ip:
        ROUTER_IP = user_ip
    else:
        ROUTER_IP = default_ip
        
    print(f"[*] RouterBOARD set to: {ROUTER_IP}")
    
    # 1. Scan for APs
    print(f"[*] Scanning for wireless Access Points on {ROUTER_IP}...")
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
    
    # 3. Configure Port Forwarding
    while True:
        target_port_str = input("Enter destination port (default: 80): ").strip()
        if not target_port_str:
            target_port = 80
            break
        try:
            target_port = int(target_port_str)
            if 0 < target_port <= 65535:
                break
            print("[-] Invalid range. Enter a valid port (1-65535).")
        except ValueError:
            print("[-] Please enter a valid integer.")

    default_proxy_port = target_port + 1000
    while True:
        forwarded_port_str = input(f"Enter proxy port (default: {default_proxy_port}): ").strip()
        if not forwarded_port_str:
            forwarded_port = default_proxy_port
            break
        try:
            forwarded_port = int(forwarded_port_str)
            if 0 < forwarded_port <= 65535:
                break
            print("[-] Invalid range. Enter a valid port (1-65535).")
        except ValueError:
            print("[-] Please enter a valid integer.")

    # Connect to Selected SSID immediately to run DHCP discovery
    print(f"\n[*] Connecting wlan1 to SSID \"{ssid_to_use}\"...")
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
        
    # Check if proxy.local resolves to ROUTER_IP
    proxy_resolves = False
    try:
        if socket.gethostbyname("proxy.local") == ROUTER_IP:
            proxy_resolves = True
    except socket.gaierror:
        pass

    print(f"\n[*] Proxy configuration summary:")
    if proxy_resolves:
        print(f"    - Proxy Entry Point: http://proxy.local:{forwarded_port}")
    else:
        print(f"    - Proxy Entry Point: http://{ROUTER_IP}:{forwarded_port} (or http://proxy.local:{forwarded_port})")
    print(f"    - Proxy Target Point: http://{target_ap_ip}:{target_port}")
    
    # 4. Apply Configurations to the RouterBOARD
    print("\n[*] Applying proxy gateway rules to the RouterBOARD...")
    try:
        # Pre-clean existing rules
        run_ssh_cmd("/ip firewall nat remove [find comment=\"sta-proxy-forward\"]")
        run_ssh_cmd("/ip firewall nat remove [find comment=\"sta-proxy-masquerade\"]")
        
        # Connect to Selected SSID
        print(f"[*] Connecting wlan1 to SSID \"{selected_net['ssid']}\"...")
        run_ssh_cmd(f"/interface wireless set [find name=wlan1] ssid=\"{selected_net['ssid']}\" mode=station frequency=auto")
        
        # Configure Static IP for local subnet (assuming target_ap_ip is on a /24 subnet, let's use .10)
        subnet_prefix = ".".join(target_ap_ip.split(".")[:3])
        static_client_ip = f"{subnet_prefix}.10"
        print(f"[*] Assigning static IP {static_client_ip}/24 to wlan1...")
        # Remove any existing static IPs on wlan1 in that subnet first to avoid duplicate errors
        run_ssh_cmd(f"/ip address remove [find interface=wlan1 and address=\"{static_client_ip}/24\"]")
        run_ssh_cmd(f"/ip address add address={static_client_ip}/24 interface=wlan1")
        
        # Configure NAT Port Forwarding Rules
        print(f"[*] Creating dstnat port-forwarding rule ({ROUTER_IP}:{forwarded_port} -> {target_ap_ip}:{target_port})...) (Mapped to proxy.local)")
        run_ssh_cmd(f"/ip firewall nat add chain=dstnat dst-port={forwarded_port} protocol=tcp action=dst-nat to-addresses={target_ap_ip} to-ports={target_port} comment=\"sta-proxy-forward\"")
        run_ssh_cmd(f"/ip firewall nat add chain=srcnat out-interface=wlan1 action=masquerade comment=\"sta-proxy-masquerade\"")
        
    except Exception as e:
        print(f"[-] Configuration error: {e}")
        clean_routerboard_rules()
        sys.exit(1)
        
    # 5. Monitoring Loop
    print("\n" + "=" * 60)
    print(f" [+] PROXY GATEWAY IS LIVE AND ACTIVE!")
    print(f"     Primary URL: http://proxy.local:{forwarded_port}")
    print(f"     Backup URL:  http://{ROUTER_IP}:{forwarded_port}")
    if not proxy_resolves:
        print("\n [!] To make http://proxy.local work on your Mac, run:")
        print(f"     echo '{ROUTER_IP} proxy.local' | sudo tee -a /etc/hosts")
    print("=" * 60)
    print("Press Ctrl+C to disconnect and stop the proxy.")
    
    try:
        while True:
            # Monitor wireless link status periodically
            try:
                reg_table = run_ssh_cmd("/interface wireless registration-table print")
                if selected_net['mac'].lower() in reg_table.lower():
                    # Extract active signal strength
                    sig_match = re.search(r"-\d+dBm", reg_table)
                    sig_str = sig_match.group(0) if sig_match else "connected"
                    print(f"[{time.strftime('%H:%M:%S')}] Link Status: Active | Signal: {sig_str}", end="\r")
                else:
                    print(f"[{time.strftime('%H:%M:%S')}] Link Status: Connecting / Searching...", end="\r")
            except Exception:
                pass
            time.sleep(2)
    except KeyboardInterrupt:
        print("\n\n[!] Interrupt received.")
    finally:
        clean_routerboard_rules()
        print("\n[+] Exited cleanly. Goodbye!")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n[-] Fatal error: {e}")
        sys.exit(1)

