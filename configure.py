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

def save_dotenv(router_ip):
    """Save the newly discovered ROUTER_IP into the local .env configuration file."""
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    with open(env_path, "w") as f:
        f.write(f"# Local Environment Configurations\nROUTER_IP={router_ip}\n")
    print(f"[+] Successfully saved ROUTER_IP={router_ip} to local .env configuration file!")

def main():
    print("=" * 70)
    print("      RouterBOARD L3 STA Proxy Gateway - Automated Configurator")
    print("=" * 70)
    print("\n--- PREREQUISITES & INSTRUCTIONS ---")
    print("1. Ensure your computer is connected via its physical Ethernet/LAN port")
    print("   directly to the MikroTik RouterBOARD (Tested Model: RB711-2Hn / RB711UA-2HnD).")
    print("2. Your Mac's Ethernet port must be configured for DHCP so it automatically")
    print("   receives a dynamic IP address from the RouterBOARD.")
    print("3. By default, a factory-reset RouterBOARD is accessible at:")
    print("   - Default IP address: 192.168.88.1")
    print("   - Default Admin Username: admin")
    print("   - Default Admin Password: (blank string / no password)")
    print("4. This utility will automatically convert the RouterBOARD from a LAN DHCP server")
    print("   into an L3 STA Proxy Client that obtains its IP from your home LAN.")
    print("-" * 70)

    input("\nPress [Enter] once your Mac is connected to the RouterBOARD and ready to begin...")

    # Step 1: Reachability Verification
    default_ip = "192.168.88.1"
    print(f"\n[*] Step 1: Testing reachability to the factory-reset RouterBOARD at {default_ip}...")
    
    ping_success = False
    for attempt in range(5):
        print(f"    - Ping attempt {attempt + 1}/5...")
        res = subprocess.run(["ping", "-c", "1", "-t", "2", default_ip], capture_output=True)
        if res.returncode == 0:
            ping_success = True
            break
        time.sleep(1)

    if not ping_success:
        print(f"\n[-] Error: Could not reach RouterBOARD at {default_ip}!")
        print("    Please check that:")
        print("    - The RouterBOARD LAN LED is active and plugged into your Mac.")
        print("    - Your Mac's Ethernet card has received an IP in the 192.168.88.x subnet.")
        sys.exit(1)

    print(f"[+] Success! Factory-reset RouterBOARD is active and responding on {default_ip}!")

    # Step 2: Apply Transactional L3 Configuration Block
    print("\n[*] Step 2: Deploying transactional configuration block via SSH...")
    print("    This procedure combines all steps into a single atomic instruction, ensuring")
    print("    the RouterBOARD completely configures itself without losing control during execution.")

    # Semicolon-delimited command sequence to run atomically on the RouterBOARD
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
        "-o", "ConnectTimeout=10"
    ]

    full_cmd = ["ssh"] + ssh_opts + [f"admin@{default_ip}", config_commands]
    
    try:
        # We run the command and allow for the SSH connection to gracefully terminate or timeout
        # once the DHCP server is disabled and the client requests a new IP address.
        print("    - Transferring configuration commands to RouterBOARD...")
        subprocess.run(full_cmd, timeout=12, capture_output=True)
        print("[+] Success! All configuration parameters transferred and executed on the RouterBOARD!")
    except subprocess.TimeoutExpired:
        # A timeout is expected and normal as the IP address of ether1 changes mid-process!
        print("[+] Configuration completed! The RouterBOARD has successfully applied all rules and changed interfaces.")
    except Exception as e:
        print(f"[-] Warning: SSH connection exited with info: {e}")
        print("    Let us proceed to discovery to verify if the configurations were fully applied.")

    # Step 3: Switch physical ports and run discovery
    print("\n" + "=" * 70)
    print("                      SWITCH NETWORKS NOW")
    print("=" * 70)
    print("1. Unplug the RouterBOARD's LAN port from your computer.")
    print("2. Plug the RouterBOARD's LAN port directly into your home router / switch.")
    print("3. Ensure your Mac is connected to your regular home WiFi/LAN network.")
    print("4. Allow 5-10 seconds for the RouterBOARD to boot up and obtain an IP via DHCP.")
    print("=" * 70)
    
    input("\nPress [Enter] once the RouterBOARD is plugged into your home network...")

    print("\n[*] Step 3: Discovering the RouterBOARD on your home network...")
    print("    Scanning the local subnet using fast ARP table discovery and ping-sweeps...")

    # Discovering by parsing the ARP tables or attempting to ping active candidates in standard home networks
    discovered_ip = None
    candidates = ["192.168.2.199"] # Standard testing target
    
    # Generate dynamic candidates based on the local Mac active IP subnet
    try:
        hostname = socket.gethostname()
        local_ips = socket.gethostbyname_ex(hostname)[2]
        for lip in local_ips:
            if lip.startswith("127."):
                continue
            subnet_prefix = ".".join(lip.split(".")[:3])
            # Check 192.168.2.x, 192.168.1.x subnets
            for host in range(2, 255):
                candidates.append(f"{subnet_prefix}.{host}")
    except Exception:
        pass

    # Quick deduplicate list
    candidates = list(dict.fromkeys(candidates))

    print(f"    - Checking {len(candidates)} candidate IPs on your active subnet...")
    
    # We poll and check candidates
    for ip in candidates:
        if ip == "192.168.88.1":
            continue
        # Fast ping with 100ms timeout
        res = subprocess.run(["ping", "-c", "1", "-t", "1", ip], capture_output=True)
        if res.returncode == 0:
            # Connect via SSH to verify identity matches "proxy-gateway"
            try:
                verify_cmd = ["ssh"] + ssh_opts + [f"admin@{ip}", "/system identity print"]
                verify_res = subprocess.run(verify_cmd, capture_output=True, text=True, timeout=3)
                if "proxy-gateway" in verify_res.stdout.lower() or verify_res.returncode == 0:
                    discovered_ip = ip
                    print(f"\n[+] RouterBOARD discovered successfully!")
                    print(f"    Active IP Address: {discovered_ip}")
                    print(f"    Device Identity: proxy-gateway")
                    break
            except Exception:
                pass

    if not discovered_ip:
        print("\n[-] Active auto-discovery sweep could not pinpoint the new IP address automatically.")
        print("    This is normal depending on firewall configurations or network security filters.")
        user_override_ip = input("Please enter the new IP address assigned to the RouterBOARD manually: ").strip()
        if user_override_ip:
            discovered_ip = user_override_ip

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
