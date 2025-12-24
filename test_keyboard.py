"""
Keyboard Test Script - Identifies key names for configuration.

Press any key to see its name. Press Ctrl+C or Escape to exit.
"""

import keyboard

print("Keyboard Test Script")
print("=" * 40)
print("Press any key to see its name.")
print("Press Escape or Ctrl+C to exit.")
print("=" * 40)
print()

def on_key(event):
    if event.event_type == "down":
        print(f"Key pressed: '{event.name}' (scan code: {event.scan_code})")

keyboard.hook(on_key)

try:
    keyboard.wait("escape")
except KeyboardInterrupt:
    pass

print("\nExiting...")
keyboard.unhook_all()
