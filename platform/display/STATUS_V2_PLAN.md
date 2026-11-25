# Status UI v2

Read-only source of actual BlueZ/PipeWire observations, optional battery, RSSI, volume, HFP/A2DP profile. The legacy MTSTATUS1 renderer currently rejects these additional fields; do not deploy the new publisher until the renderer and its preview tests accept them. The new publisher is not a replacement for authoritative Core state and cannot declare live audio readiness.
