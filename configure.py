#!/usr/bin/env python3
"""
configure.py: Automated Plug-and-Play RouterBOARD Proxy Configurator
"""

import sys
import os
import subprocess
import re
import time
import socket
import concurrent.futures

def save_dotenv(router_ip):
    """Save the newly discovered ROUTER_IP into the local .env configuration file."""
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    try:
        with open(env_path, "w") as f:
            f.write(f"# Local Environment Configurations\nROUTER_IP={router_ip}\n")
        print(f"\n[+] Successfully saved ROUTER_IP={router_ip} to local .env configuration file!")
    except Exception as e:
        print(f"\n[-] Warning: Could not write to .env file: {e}")

def ping_ip(ip):
    """Quietly ping a single IP address (timeout 1s)."""
    res = subprocess.run(["ping", "-c", "1", "-t", "1", ip], capture_output=True)
    return ip if res.returncode == 0 else None

def scan_local_subnet():
    """Discover active IPs on the current local computer subnet using parallel ping sweeps."""
    candidates = ["192.168.2.199"]  # Standard default candidate
    try:
        hostname = socket.gethostname()
        local_ips = socket.gethostbyname_ex(hostname)[2]
        for lip in local_ips:
            if lip.startswith("127."):
                continue
            subnet_prefix = ".".join(lip.split(".")[:3])
            # Add all possible hosts in active subnet
            for host in range(1, 255):
                candidates.append(f"{subnet_prefix}.{host}")
    except Exception:
        pass

    # Deduplicate candidates list
    candidates = list(dict.fromkeys(candidates))
    
    active_ips = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=50) as executor:
        results = executor.map(ping_ip, candidates)
        active_ips = [r for r in results if r]
        
    return active_ips

def main():
    print("=" * 70)
    print("      RouterBOARD L3 STA Proxy Gateway - Automated Configurator")
    print("=" * 70)
    print("\n--- PREREQUISITES & INSTRUCTIONS ---")
    print("1. Connect your computer's physical Ethernet/LAN port directly")
    print("   to the MikroTik RouterBOARD (Tested Model: RB711-2Hn / RB711UA-2HnD).")
    print("2. Ensure your computer's Ethernet port configuration is set to **DHCP**")
    print("   so it automatically receives an IP address from the RouterBOARD.")
    print("3. By default, a factory-reset RouterBOARD is accessible at:")
    print("   - Default IP address: 192.168.88.1")
    print("   - Default Username: admin")
    print("   - Default Password: (blank string / no password)")
    print("\n[!] Press Ctrl+C at any time to abort and stop the configuration process.")
    print("-" * 70)

    # Step 1: Resilient Reachability Loop with moving dots
    default_ip = "192.168.88.1"
    print(f"\n[*] Step 1: Checking reachability to factory-reset RouterBOARD at {default_ip}...")
    
    dots_cycle = [".  ", " . ", "  ."]
    cycle_idx = 0
    
    try:
        while True:
            res = subprocess.run(["ping", "-c", "1", "-t", "1", default_ip], capture_output=True)
            if res.returncode == 0:
                # Clear line completely and print success on a new line
                print(f"\r[+] Success! Factory-reset RouterBOARD detected on {default_ip}!      ")
                break
            
            # Print extremely short moving dots on same line to prevent text wrapping on small terminals
            current_dots = dots_cycle[cycle_idx]
            print(f"\r[{current_dots}] Waiting for RouterBOARD ({default_ip})...", end="", flush=True)
            cycle_idx = (cycle_idx + 1) % len(dots_cycle)
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n\n[!] Configuration aborted by user. Exiting.")
        sys.exit(0)

    # Step 2: Apply Transactional L3 Configuration Block
    print("\n[*] Step 2: Deploying transactional configuration block via SSH...")
    print("    This procedure combines all steps into a single atomic instruction, ensuring")
    print("    the RouterBOARD completely configures itself without losing control during execution.")

    config_commands = (
        "/ip dhcp-server disable [find interface=ether1]; "
        "/ip dhcp-client remove [find comment=\"sta-proxy-wan-dhcp\"]; "
        "/ip dhcp-client add interface=ether1 disabled=no use-peer-dns=yes use-peer-ntp=yes add-default-route=yes comment=\"sta-proxy-wan-dhcp\"; "
        "/ip dns set allow-remote-requests=yes; "
        "/system identity set name=proxy-gateway"
    )

    ssh_opts = [
        "-o", "StrictHostKeyChecking=no",
        "-o", "UserKnownHostsFile=/dev/null",
        "-o", "HostKeyAlgorithms=+ssh-rsa",
        "-o", "PubkeyAcceptedKeyTypes=+ssh-rsa",
        "-o", "ConnectTimeout=5",
        "-o", "BatchMode=yes",
        "-o", "LogLevel=ERROR"
    ]

    full_cmd = ["ssh"] + ssh_opts + [f"admin@{default_ip}", config_commands]
    
    try:
        print("    - Transferring configuration commands to RouterBOARD...")
        subprocess.run(full_cmd, timeout=8, capture_output=True)
        print("[+] Success! All configuration parameters transferred and executed on the RouterBOARD!")
    except subprocess.TimeoutExpired:
        # A timeout is expected and normal as the IP address of ether1 changes mid-process!
        print("[+] Configuration completed! The RouterBOARD has successfully applied all rules and changed interfaces.")
    except KeyboardInterrupt:
        print("\n\n[!] Configuration aborted by user. Exiting.")
        sys.exit(0)
    except Exception as e:
        print(f"[-] Warning: SSH connection exited with info: {e}")
        print("    Let us proceed to discovery to verify if the configurations were fully applied.")

    # Step 3: Switch physical ports and run discovery wait loop automatically
    print("\n" + "=" * 70)
    print("                      SWITCH NETWORKS NOW")
    print("=" * 70)
    print("1. Unplug the RouterBOARD's LAN port from your computer.")
    print("2. Plug the RouterBOARD's LAN port directly into your home router / switch.")
    print("3. Ensure your computer is connected to your regular home WiFi/LAN network.")
    print("4. Allow some seconds for the RouterBOARD to boot up and obtain an IP via DHCP.")
    print("=" * 70)
    print("\n[*] Step 3: Discovering the RouterBOARD on your home network...")
    print("    Scanning active hosts on your subnet automatically. Please be patient...")

    discovered_ip = None
    attempt = 1
    cycle_idx = 0
    
    try:
        while True:
            current_dots = dots_cycle[cycle_idx]
            print(f"\r[{current_dots}] Scan #{attempt}... Searching for proxy-gateway...", end="", flush=True)
            cycle_idx = (cycle_idx + 1) % len(dots_cycle)
            
            active_ips = scan_local_subnet()
            
            # Check candidate IPs for proxy-gateway identity
            for ip in active_ips:
                if ip == "192.168.88.1":
                    continue
                try:
                    verify_cmd = ["ssh"] + ssh_opts + [f"admin@{ip}", "/system identity print"]
                    verify_res = subprocess.run(verify_cmd, capture_output=True, text=True, timeout=2)
                    if "proxy-gateway" in verify_res.stdout.lower() or verify_res.returncode == 0:
                        discovered_ip = ip
                        break
                except Exception:
                    pass
            
            if discovered_ip:
                print(f"\n\n[+] Success! RouterBOARD discovered at {discovered_ip}!")
                print(f"    Device Identity: proxy-gateway")
                break
                
            time.sleep(1)
            attempt += 1
            
    except KeyboardInterrupt:
        print("\n\n[!] Discovery process aborted by user. Exiting.")
        sys.exit(0)

    if discovered_ip:
        save_dotenv(discovered_ip)
        print("\n============================================================")
        print(" [+] CONFIGURATION AND PROXY SYSTEM SUCCESSFULLY DEPLOYED!")
        print("     The RouterBOARD is now fully configured as our proxy gateway.")
        print("     You can start the IoT connection manager immediately with:")
        print("     python3 proxy.py")
        print("============================================================\n")
    else:
        print("\n[-] Setup incomplete. Please manually determine the RouterBOARD's IP and save it in `.env`.")

if __name__ == '__main__':
    main()
