"""
Run this ONCE to find your scale.
Step on the scale while this script runs.

Usage:
    python3 scan.py

macOS note: MAC addresses are hidden by CoreBluetooth. You'll see a UUID
instead. That's fine — listener.py identifies the scale by name on macOS.
On Linux/Pi, you'll get a real MAC address to put in config.json.
"""
import asyncio
import platform
from bleak import BleakScanner

IS_MACOS = platform.system() == "Darwin"


async def scan():
    print("Scanning for BLE devices for 15 seconds...")
    print("Step on your scale NOW.\n")

    devices = await BleakScanner.discover(timeout=30.0)

    renpho_devices = []
    print("All discovered devices:")
    for d in devices:
        name = d.name or "(unnamed)"
        print(f"  {d.address}  {name}")
        if any(kw in name.upper() for kw in ("RENPHO", "ES-26", "SCALE", "MIBFS", "YUNMAI")):
            renpho_devices.append(d)

    print()
    if renpho_devices:
        print("==> Likely scale devices found:")
        for d in renpho_devices:
            print(f"  Address: {d.address}  Name: {d.name}")
        print()
        if IS_MACOS:
            print("You're on macOS — the address shown is a UUID, not a MAC.")
            print("listener.py will find the scale by name automatically.")
            print("Just make sure 'scale_name_hint' in config.json matches the start of the name above.")
        else:
            print("Copy the address above into config.json as 'scale_mac'.")
    else:
        print("No obvious scale found. Check the full list above.")
        print("If you see an unfamiliar device while the scale was on, that's likely it.")


asyncio.run(scan())
