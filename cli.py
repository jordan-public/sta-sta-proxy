#!/usr/bin/env python3
"""
sta-proxy-cli: Interactive AP Discovery & RouterBOARD Proxy Gateway Controller
"""

import sys
import os
import subprocess
import re
import time

ROUTER_IP = "192.168.2.199"
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
                
                networks.append({
                    "mac": mac,
                    "ssid": ssid,
                    "signal": sig
                })
    return networks


def main():
    print("=" * 60)
    print(" sta-proxy-cli: RouterBOARD IoT Proxy Connection Manager")
    print("=" * 60)
    
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
            
    print(f"\n[+] Selected AP: {selected_net['ssid']} ({selected_net['mac']})")
    
    # 3. Configure Port Forwarding Offset
    while True:
        port_offset_str = input("Enter port forwarding offset (default: 1000): ").strip()
        if not port_offset_str:
            port_offset = 1000
            break
        try:
            port_offset = int(port_offset_str)
            if 0 < port_offset < 60000:
                break
            print("[-] Invalid range. Enter a valid port offset.")
        except ValueError:
            print("[-] Please enter a valid integer.")
            
    target_port = 80
    forwarded_port = target_port + port_offset
    target_ap_ip = "192.168.4.1" # Standard default for Tasmota, Rover Tank, etc.
    
    # Prompt for Target AP IP overrides
    ip_override = input(f"Enter target AP gateway IP (default: {target_ap_ip}): ").strip()
    if ip_override:
        target_ap_ip = ip_override
        
    print(f"\n[*] Proxy configuration summary:")
    print(f"    - Proxy Entry Point: http://{ROUTER_IP}:{forwarded_port}")
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
        print(f"[*] Creating dstnat port-forwarding rule (port {forwarded_port} -> {target_ap_ip}:80)...")
        run_ssh_cmd(f"/ip firewall nat add chain=dstnat dst-port={forwarded_port} protocol=tcp action=dst-nat to-addresses={target_ap_ip} to-ports=80 comment=\"sta-proxy-forward\"")
        run_ssh_cmd(f"/ip firewall nat add chain=srcnat out-interface=wlan1 action=masquerade comment=\"sta-proxy-masquerade\"")
        
    except Exception as e:
        print(f"[-] Configuration error: {e}")
        clean_routerboard_rules()
        sys.exit(1)
        
    # 5. Monitoring Loop
    print("\n" + "=" * 60)
    print(f" [+] PROXY GATEWAY IS LIVE AND ACTIVE!")
    print(f"     Access in your web browser: http://{ROUTER_IP}:{forwarded_port}")
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

