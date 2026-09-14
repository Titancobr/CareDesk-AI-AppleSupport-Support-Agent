"""AppleCare Knowledge Base and Diagnostic Rules Engine.

Provides authoritative SOPs, warranty terms, accidental damage deductibles,
diagnostic steps, and device registries for AppleCare support.
"""
from __future__ import annotations

from typing import Any, Optional

# Official AppleCare+ Deductible Matrix (US standard / international equivalents)
DEDUCTIBLE_MATRIX = {
    "screen_or_back_glass": {
        "applecare_plus": 29.00,
        "out_of_warranty_min": 199.00,
        "out_of_warranty_max": 379.00,
        "description": "Screen or back glass damage (iPhone 12 through 16 Pro Max)"
    },
    "other_accidental_damage": {
        "applecare_plus": 99.00,
        "out_of_warranty_min": 299.00,
        "out_of_warranty_max": 649.00,
        "description": "Any other accidental physical or liquid damage"
    },
    "theft_and_loss": {
        "applecare_plus": 149.00,
        "out_of_warranty_min": 799.00,
        "out_of_warranty_max": 1599.00,
        "description": "Theft or loss replacement (requires Find My enabled at time of incident)"
    },
    "battery_service": {
        "applecare_plus": 0.00,  # Free if health < 80% under active AppleCare+
        "out_of_warranty_min": 89.00,
        "out_of_warranty_max": 249.00,
        "description": "Battery replacement (free under AppleCare+ if Maximum Capacity < 80%)"
    },
    "mac_screen_or_enclosure": {
        "applecare_plus": 99.00,
        "out_of_warranty_min": 499.00,
        "out_of_warranty_max": 899.00,
        "description": "MacBook display or external enclosure damage"
    },
    "mac_other_damage": {
        "applecare_plus": 299.00,
        "out_of_warranty_min": 699.00,
        "out_of_warranty_max": 1499.00,
        "description": "Mac logic board, liquid spill, or internal damage"
    },
    "ipad_accidental_damage": {
        "applecare_plus": 49.00,
        "out_of_warranty_min": 249.00,
        "out_of_warranty_max": 899.00,
        "description": "iPad display or structural damage"
    },
    "apple_watch_damage": {
        "applecare_plus": 69.00,
        "out_of_warranty_min": 199.00,
        "out_of_warranty_max": 499.00,
        "description": "Apple Watch Series & Ultra accidental damage"
    },
    "airpods_damage": {
        "applecare_plus": 29.00,
        "out_of_warranty_min": 89.00,
        "out_of_warranty_max": 199.00,
        "description": "AirPods or charging case replacement per incident"
    }
}

# Authoritative Device Troubleshooting Standard Operating Procedures (SOPs)
APPLE_TROUBLESHOOTING_SOPS = {
    "force_restart_iphone": {
        "title": "Force Restart iPhone (Face ID / iPhone 8 and later)",
        "category": "power_boot",
        "official_doc": "Apple Support HT201559",
        "steps": [
            "Press and quickly release the Volume Up button.",
            "Press and quickly release the Volume Down button.",
            "Press and hold the Side button.",
            "Keep holding until the Apple logo appears on screen (approx. 10–15 seconds), then release."
        ],
        "notes": "Do not release the Side button when 'slide to power off' appears; wait for the Apple logo."
    },
    "water_liquid_exposure": {
        "title": "Liquid Exposure & Liquid Contact Indicator (LCI) Triage",
        "category": "accidental_damage",
        "official_doc": "Apple Support HT204104",
        "steps": [
            "Immediately turn off the device and disconnect all cables, accessories, and chargers.",
            "Tap the device gently against your hand with the connector facing down to remove excess liquid.",
            "Leave the device in a dry area with some airflow for at least 24–48 hours.",
            "Inspect the Liquid Contact Indicator (LCI) inside the SIM tray slot using a flashlight. If pink or red, internal liquid contact has occurred.",
            "Do NOT put the device in uncooked rice or use an external heat source (hairdryer, oven)."
        ],
        "notes": "Liquid damage is not covered under Apple's 1-Year Limited Warranty, but is covered under AppleCare+ with a $99 accidental damage deductible."
    },
    "battery_health_diagnostics": {
        "title": "Battery Drain & Maximum Capacity Diagnostic",
        "category": "battery_power",
        "official_doc": "Apple Support HT208387",
        "steps": [
            "Open Settings > Battery > Battery Health & Charging.",
            "Check 'Maximum Capacity'. If Maximum Capacity is below 80%, battery service is recommended.",
            "Check for 'Peak Performance Capability' messages indicating performance management throttling.",
            "Review 'Battery Usage by App' over the last 24 hours and 10 days to detect background activity spikes.",
            "Enable 'Optimized Battery Charging' to reduce battery aging."
        ],
        "notes": "Under active AppleCare+, battery replacement is 100% free ($0 deductible) when maximum capacity drops below 80%."
    },
    "display_touch_issues": {
        "title": "Display Unresponsive or Ghost Touching",
        "category": "display_touch",
        "official_doc": "Apple Support HT201406",
        "steps": [
            "Remove any screen protectors, tempered glass, or cases that may interfere with touch sensors.",
            "Disconnect all Lightning or USB-C charging cables (faulty third-party chargers can induce capacitance noise).",
            "Perform a force restart.",
            "If touch remains unresponsive in specific areas, schedule an Apple Authorized Service diagnostic to verify Multi-Touch digitizer integrity."
        ],
        "notes": "Screen replacement under AppleCare+ is $29."
    },
    "airpods_audio_connectivity": {
        "title": "AirPods Reset and Audio Troubleshooting",
        "category": "audio_bluetooth",
        "official_doc": "Apple Support HT209463",
        "steps": [
            "Put both AirPods in the charging case and close the lid for 30 seconds.",
            "Open the lid and check the status light.",
            "On your paired iPhone, go to Settings > Bluetooth, tap the (i) info icon next to your AirPods, and tap 'Forget This Device'.",
            "With the lid open, press and hold the setup button on the back of the case for about 15 seconds until the status light flashes amber, then white.",
            "Bring AirPods near your iPhone and follow the on-screen reconnect prompt."
        ],
        "notes": "If one earbud produces no sound after reset, clean the microphone and speaker meshes gently with a dry cotton swab."
    },
    "mac_dfu_recovery": {
        "title": "Mac Startup Diagnostics & macOS Recovery (Apple Silicon / Intel)",
        "category": "mac_os",
        "official_doc": "Apple Support HT204904",
        "steps": [
            "For Apple Silicon (M1/M2/M3/M4): Shut down Mac completely. Press and hold the power button until 'Loading startup options' appears.",
            "Select 'Options', then click 'Continue' to enter macOS Recovery.",
            "Run Disk Utility First Aid on the boot volume ('Macintosh HD') to verify file system integrity.",
            "To run Apple Diagnostics: From startup options, press and hold Command + D until diagnostic mode begins."
        ],
        "notes": "Hardware logic board repair under AppleCare+ is $299."
    },
    "activation_lock_find_my": {
        "title": "Turn Off Find My & Activation Lock for AppleCare Service",
        "category": "account_security",
        "official_doc": "Apple Support HT201441",
        "steps": [
            "Before sending any device for repair, Find My must be turned off (security requirement).",
            "On device: Settings > [Your Name] > Find My > Find My iPhone > toggle OFF and enter Apple Account password.",
            "Remotely via web: Sign in to iCloud.com/find > All Devices > select device > click 'Remove from Account'.",
            "Create a full iCloud or Mac backup, then Erase All Content and Settings (Settings > General > Transfer or Reset iPhone)."
        ],
        "notes": "Apple Authorized Service Providers cannot replace or service a logic board while Activation Lock is active."
    }
}

# Mock Authoritative Serial Number Registry for Testing
SERIAL_DATABASE = {
    "F17X9K02MND6": {
        "serial": "F17X9K02MND6",
        "device": "iPhone 15 Pro Max 256GB (Natural Titanium)",
        "purchase_date": "2024-03-15",
        "coverage_type": "AppleCare+ with Theft and Loss",
        "status": "Active",
        "expiry_date": "2026-03-15",
        "incident_count": 0,
        "battery_health": 94,
        "eligible_deductibles": {
            "screen": 29.00,
            "other_damage": 99.00,
            "theft_loss": 149.00,
            "battery": 0.00
        }
    },
    "C02G80P0MD6R": {
        "serial": "C02G80P0MD6R",
        "device": "MacBook Pro 16\" (M3 Max, 36GB, 1TB Space Black)",
        "purchase_date": "2023-11-20",
        "coverage_type": "AppleCare+",
        "status": "Active",
        "expiry_date": "2026-11-20",
        "incident_count": 1,
        "battery_health": 91,
        "eligible_deductibles": {
            "screen_enclosure": 99.00,
            "other_damage": 299.00,
            "battery": 0.00
        }
    },
    "H98KL019PQ23": {
        "serial": "H98KL019PQ23",
        "device": "iPhone 13 128GB (Midnight)",
        "purchase_date": "2021-10-12",
        "coverage_type": "Out of Warranty (Standard Limited Warranty Expired)",
        "status": "Expired",
        "expiry_date": "2022-10-12",
        "incident_count": 0,
        "battery_health": 74,  # Eligible for battery replacement
        "eligible_deductibles": {
            "screen": 279.00,
            "other_damage": 449.00,
            "battery": 89.00
        }
    },
    "W45P088XQ19A": {
        "serial": "W45P088XQ19A",
        "device": "Apple Watch Ultra 2 (Titanium, Orange Ocean Band)",
        "purchase_date": "2024-05-02",
        "coverage_type": "AppleCare+",
        "status": "Active",
        "expiry_date": "2026-05-02",
        "incident_count": 0,
        "battery_health": 98,
        "eligible_deductibles": {
            "accidental_damage": 69.00,
            "battery": 0.00
        }
    }
}


def lookup_warranty(serial_or_model: str) -> dict[str, Any]:
    """Look up AppleCare coverage and warranty details by serial or model."""
    clean_key = serial_or_model.strip().upper()
    if clean_key in SERIAL_DATABASE:
        return SERIAL_DATABASE[clean_key]
    
    lower = serial_or_model.lower()
    is_iphone = "iphone" in lower or len(clean_key) == 12
    is_mac = "mac" in lower or "macbook" in lower
    is_watch = "watch" in lower
    is_airpods = "airpod" in lower

    device_name = (
        "iPhone (Recent Generation)" if is_iphone
        else "MacBook Pro / Air" if is_mac
        else "Apple Watch" if is_watch
        else "AirPods Pro" if is_airpods
        else "Apple Device"
    )

    return {
        "serial": clean_key,
        "device": device_name,
        "purchase_date": "Estimated within last 12 months",
        "coverage_type": "Standard 1-Year Limited Warranty (Check Apple Support for AppleCare+ add-on)",
        "status": "Eligible for Diagnostic Inspection",
        "expiry_date": "Contact Apple Support to confirm official registration",
        "incident_count": 0,
        "battery_health": 92,
        "eligible_deductibles": {
            "screen_under_applecare": 29.00,
            "other_damage_under_applecare": 99.00,
            "standard_out_of_warranty_estimate": 299.00 if is_iphone else 499.00 if is_mac else 199.00
        }
    }


def find_matching_sop(query: str) -> list[dict[str, Any]]:
    """Match customer query with relevant Apple Support SOPs."""
    q = query.lower()
    matched = []

    if any(k in q for k in ["water", "liquid", "wet", "dropped in", "coffee", "spill", "tea", "swimming", "rain"]):
        matched.append(APPLE_TROUBLESHOOTING_SOPS["water_liquid_exposure"])
    
    if any(k in q for k in ["won't turn on", "wont turn on", "black screen", "frozen", "restart", "reboot", "apple logo", "stuck"]):
        matched.append(APPLE_TROUBLESHOOTING_SOPS["force_restart_iphone"])
    
    if any(k in q for k in ["battery", "drain", "draining", "charge", "charging", "health", "80%", "overheating", "hot"]):
        matched.append(APPLE_TROUBLESHOOTING_SOPS["battery_health_diagnostics"])
        
    if any(k in q for k in ["screen", "display", "touch", "flicker", "lines", "cracked", "glass", "ghost touch"]):
        matched.append(APPLE_TROUBLESHOOTING_SOPS["display_touch_issues"])
        
    if any(k in q for k in ["airpod", "airpods", "earbuds", "no sound", "audio", "one side", "static"]):
        matched.append(APPLE_TROUBLESHOOTING_SOPS["airpods_audio_connectivity"])

    if any(k in q for k in ["mac", "macbook", "kernel panic", "recovery", "disk utility", "startup", "os"]):
        matched.append(APPLE_TROUBLESHOOTING_SOPS["mac_dfu_recovery"])

    if any(k in q for k in ["find my", "activation lock", "apple id", "password", "sign in", "reset", "erase"]):
        matched.append(APPLE_TROUBLESHOOTING_SOPS["activation_lock_find_my"])

    return matched
