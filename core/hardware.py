"""
Veo Studio AI PRO - Multi-Factor Hardware Fingerprint Generator

Collects hardware identifiers (MAC Address, Windows Machine GUID, Processor ID, Computer Name)
to generate a tamper-resistant Hardware Fingerprint (MAC ID) for device licensing.
"""

import os
import sys
import uuid
import hashlib
import logging
import platform

logger = logging.getLogger(__name__)


def get_mac_address() -> str:
    """Get primary network interface MAC address in formatted string (XX:XX:XX:XX:XX:XX)"""
    try:
        mac_num = uuid.getnode()
        mac_hex = f"{mac_num:012x}"
        return ":".join(mac_hex[i:i+2] for i in range(0, 12, 2)).upper()
    except Exception as e:
        logger.warning(f"Lỗi lấy MAC address: {e}")
        return "00:00:00:00:00:00"


def get_windows_machine_guid() -> str:
    """Read Windows Cryptography MachineGuid from Registry"""
    if sys.platform != "win32":
        return "NON-WINDOWS-ENV"
    
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Cryptography",
            0,
            winreg.KEY_READ | winreg.KEY_WOW64_64KEY
        )
        guid, _ = winreg.QueryValueEx(key, "MachineGuid")
        winreg.CloseKey(key)
        return str(guid).strip()
    except Exception as ex:
        logger.warning(f"Không thể đọc Windows MachineGuid từ Registry: {ex}")
        return "UNKNOWN-MACHINE-GUID"


def get_device_name() -> str:
    """Get friendly computer device name"""
    try:
        return platform.node() or os.environ.get("COMPUTERNAME", "Desktop-PC")
    except Exception:
        return "Desktop-PC"


def get_hardware_fingerprint() -> dict:
    """Generate multi-factor hardware fingerprint dictionary and formatted MAC ID key.
    
    Returns:
        dict: {
            "mac_id": "VEO-MAC-XXXX-YYYY-ZZZZ",
            "raw_mac": "AA:BB:CC:DD:EE:FF",
            "machine_guid": "...",
            "device_name": "DESKTOP-XXXX",
            "platform": "Windows-10-...",
            "fingerprint_hash": "64-char sha256"
        }
    """
    mac = get_mac_address()
    guid = get_windows_machine_guid()
    dev_name = get_device_name()
    plat_info = f"{platform.system()}-{platform.release()}-{platform.machine()}"
    proc_info = platform.processor() or "CPU"

    # Combine multi-factor hardware attributes
    combined_raw = f"{mac}|{guid}|{proc_info}|{plat_info}"
    sha256_hash = hashlib.sha256(combined_raw.encode("utf-8")).hexdigest().upper()

    # Formatted user-friendly MAC ID: VEO-MAC-XXXX-YYYY-ZZZZ
    formatted_mac_id = f"VEO-MAC-{sha256_hash[:4]}-{sha256_hash[4:8]}-{sha256_hash[8:12]}"

    return {
        "mac_id": formatted_mac_id,
        "raw_mac": mac,
        "machine_guid": guid,
        "device_name": dev_name,
        "platform": plat_info,
        "fingerprint_hash": sha256_hash
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    info = get_hardware_fingerprint()
    print("=== Hardware Fingerprint Info ===")
    for k, v in info.items():
        print(f"{k}: {v}")
