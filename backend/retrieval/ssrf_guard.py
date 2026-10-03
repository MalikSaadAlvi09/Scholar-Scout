"""
SSRF Protection & Network Target Validator for ScholarScout.
Protects web fetchers and browser instances against localhost, private network,
cloud metadata endpoints (AWS/GCP/Azure/Alibaba), and non-HTTP protocols.
"""

import socket
import ipaddress
from typing import Tuple, Optional
from urllib.parse import urlparse, urljoin
from backend.logging_utils import logger

# Blocked private and reserved IPv4/IPv6 networks
BLOCKED_NETWORKS = [
    ipaddress.ip_network("0.0.0.0/8"),         # Current network (only valid as source address)
    ipaddress.ip_network("10.0.0.0/8"),        # Private network RFC 1918
    ipaddress.ip_network("100.64.0.0/10"),     # Shared Address Space RFC 6598
    ipaddress.ip_network("127.0.0.0/8"),       # Loopback addresses
    ipaddress.ip_network("169.254.0.0/16"),    # Link-local / Cloud metadata (AWS/GCP/Azure: 169.254.169.254)
    ipaddress.ip_network("172.16.0.0/12"),     # Private network RFC 1918
    ipaddress.ip_network("192.0.0.0/24"),      # IETF Protocol Assignments
    ipaddress.ip_network("192.0.2.0/24"),      # TEST-NET-1
    ipaddress.ip_network("192.168.0.0/16"),    # Private network RFC 1918
    ipaddress.ip_network("198.18.0.0/15"),     # Network benchmark testing
    ipaddress.ip_network("198.51.100.0/24"),   # TEST-NET-2
    ipaddress.ip_network("203.0.113.0/24"),    # TEST-NET-3
    ipaddress.ip_network("224.0.0.0/4"),       # Multicast
    ipaddress.ip_network("240.0.0.0/4"),       # Reserved for future use
    ipaddress.ip_network("255.255.255.255/32"),# Broadcast
    # IPv6 Blocked ranges
    ipaddress.ip_network("::/128"),            # Unspecified address
    ipaddress.ip_network("::1/128"),           # Loopback
    ipaddress.ip_network("::ffff:0:0/96"),     # IPv4-mapped IPv6
    ipaddress.ip_network("64:ff9b::/96"),      # IPv4/IPv6 translation
    ipaddress.ip_network("100::/64"),          # Discard prefix
    ipaddress.ip_network("2001:db8::/32"),     # Documentation
    ipaddress.ip_network("fc00::/7"),          # Unique local address (ULA)
    ipaddress.ip_network("fe80::/10"),         # Link-local address
    ipaddress.ip_network("ff00::/8"),          # Multicast
]

# Blocked hostnames (cloud metadata, internal services)
BLOCKED_HOSTNAMES = {
    "localhost",
    "localhost.localdomain",
    "ip6-localhost",
    "ip6-loopback",
    "metadata.google.internal",
    "metadata.internal",
    "metadata.local",
    "instance-data.ec2.internal",
    "instance-data",
    "169.254.169.254"
}

def is_safe_target_url(url: str) -> Tuple[bool, str]:
    """
    Validates that a URL is safe to fetch via HTTP or Playwright.
    Enforces HTTP/HTTPS protocol and verifies that all resolved IP addresses
    are public routable internet addresses.
    
    Returns:
        (is_safe: bool, reason: str)
    """
    if not url or not isinstance(url, str):
        return False, "Empty or invalid URL provided."

    url = url.strip()
    try:
        parsed = urlparse(url)
    except Exception as e:
        return False, f"Failed to parse URL: {e}"

    # 1. Enforce HTTP/HTTPS scheme only
    if parsed.scheme.lower() not in ("http", "https"):
        return False, f"Unsupported scheme '{parsed.scheme}'. Only http:// and https:// are permitted."

    hostname = parsed.hostname
    if not hostname:
        return False, "Missing hostname in target URL."

    hostname_clean = hostname.strip().lower().rstrip(".")

    # 2. Check blocked hostnames
    if hostname_clean in BLOCKED_HOSTNAMES:
        return False, f"Blocked target hostname '{hostname_clean}' (Internal/Metadata target)."

    # 3. Check direct IP address in URL
    try:
        ip_obj = ipaddress.ip_address(hostname_clean)
        for net in BLOCKED_NETWORKS:
            if ip_obj in net:
                return False, f"Target IP '{ip_obj}' is in restricted network range '{net}'."
        if ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_link_local or ip_obj.is_multicast or ip_obj.is_reserved:
            return False, f"Target IP '{ip_obj}' is private or reserved."
        return True, "Safe public IP address."
    except ValueError:
        # Not a raw IP literal, proceed to DNS resolution
        pass

    # 4. Resolve DNS and check all resolved IP addresses
    try:
        port = parsed.port or (443 if parsed.scheme.lower() == "https" else 80)
        addr_info = socket.getaddrinfo(hostname_clean, port, proto=socket.IPPROTO_TCP)
        
        if not addr_info:
            return False, f"Could not resolve hostname '{hostname_clean}'."

        resolved_ips = set()
        for item in addr_info:
            sockaddr = item[4]
            ip_str = sockaddr[0]
            resolved_ips.add(ip_str)

        for ip_str in resolved_ips:
            try:
                ip_obj = ipaddress.ip_address(ip_str)
                for net in BLOCKED_NETWORKS:
                    if ip_obj in net:
                        return False, f"Resolved IP '{ip_str}' for '{hostname_clean}' is in restricted network range '{net}'."
                if ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_link_local or ip_obj.is_multicast or ip_obj.is_reserved:
                    return False, f"Resolved IP '{ip_str}' for '{hostname_clean}' is private, loopback, or reserved."
            except ValueError:
                return False, f"Invalid resolved IP format: '{ip_str}'."

        return True, "Safe public domain."

    except socket.gaierror as e:
        # DNS resolution error (e.g. host not found)
        return False, f"DNS resolution failed for '{hostname_clean}': {e}"
    except Exception as e:
        return False, f"Network validation error for '{hostname_clean}': {e}"

def validate_redirect_target(source_url: str, redirect_target: str) -> Tuple[bool, str, str]:
    """
    Resolves relative redirect URLs against the source URL and validates the destination.
    Returns: (is_safe: bool, resolved_url: str, reason: str)
    """
    resolved_url = urljoin(source_url, redirect_target)
    is_safe, reason = is_safe_target_url(resolved_url)
    return is_safe, resolved_url, reason
