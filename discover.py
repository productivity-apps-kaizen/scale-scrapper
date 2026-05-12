"""
Debug tool: connects to your scale and dumps every GATT service and characteristic.
Run this after you have the MAC address from scan.py.

Usage:
    python3 discover.py XX:XX:XX:XX:XX:XX
"""
import asyncio
import sys
from bleak import BleakClient


async def dump(address: str):
    print(f"Connecting to {address}...")
    async with BleakClient(address) as client:
        print(f"Connected: {client.is_connected}\n")
        for service in client.services:
            print(f"Service: {service.uuid}  —  {service.description}")
            for char in service.characteristics:
                props = ", ".join(char.properties)
                print(f"  Char: {char.uuid}  [{props}]")
                if "read" in char.properties:
                    try:
                        val = await client.read_gatt_char(char.uuid)
                        print(f"    Value (raw): {val.hex()}  {list(val)}")
                    except Exception as e:
                        print(f"    Read error: {e}")
            print()


if len(sys.argv) < 2:
    print("Usage: python3 discover.py XX:XX:XX:XX:XX:XX")
    sys.exit(1)

asyncio.run(dump(sys.argv[1]))
