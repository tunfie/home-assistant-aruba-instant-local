# Aruba Instant Local

**0.1.0-beta.1 — publication candidate, not yet in the Marketplace catalog.**

Local Aruba Instant (AOS 8) monitoring for Home Assistant, without Telnet, SSH,
cloud access, host scripts or extra containers. Independent of any dashboard.

## Features

- UI setup and reauthentication; English and Dutch forms.
- One coordinated poll, default every 60 seconds (30–600 seconds configurable).
- AP, SSID and connected-client counts; AP channel, utilization and noise details.
- Native active/enabled Wi-Fi profile binary sensors, discovered automatically.
- Optional per-client signal sensors, disabled by default to limit visitor tracking.
- Installed firmware and upgrade-in-progress status (no firmware installation).
- TLS hostname and CA validation always enabled; secrets excluded from diagnostics.

## Compatibility

Home Assistant 2026.11 or newer. Initial live verification targets Aruba Instant
AP-305, AOS 8.13.3.0, two APs under an Instant virtual controller.
Other AOS 8 firmware/models need testing. AOS 10, Aruba Central and Instant On
use different interfaces and are **not supported** by this version.
Tables depend on the English CLI output used by the REST API.

## Prerequisites

1. Enable the controller REST API yourself using the vendor-documented
   `allow-rest-api` setting. The integration does not enable it or change accounts.
2. Reach the controller directly on its REST port, normally 4343.
3. Use a certificate whose name and issuing CA Home Assistant trusts.
   A default untrusted/self-signed certificate will fail safely. There is no
   insecure bypass toggle in this beta.
4. Have a local account authorized to run the five read commands below.
   Least-privilege account support depends on the controller firmware.
5. Know the **actual active conductor AP address**. The virtual controller IP
   can differ; enter the conductor address in its separate field.

## Install this beta manually

Copy only `custom_components/aruba_instant_local` into your Home Assistant
`config/custom_components/` directory. Restart Home Assistant, then use
Settings → Devices & services → Add integration → **Aruba Instant Local**.

Enter controller address, port, certificate hostname, conductor AP address,
username, password and polling interval. Blank certificate/AP fields use the
controller host; the fallback AP address must actually be accepted by your API.

Passwords are managed by Home Assistant config entries, not by this repository.
Home Assistant config entries/backups can contain secrets: protect them.
This integration does not add its own encryption layer.

## What entities contain

One controller device holds count sensors and firmware state.
AP details are attributes on the AP count sensor, rather than separate AP devices:
stable hardware identifiers are not available in all `show aps` outputs.
Wi-Fi profiles have separate binary sensors with their SSID and state attributes.
Per-client signal entities can be enabled individually in the entity registry;
their attributes include current AP, SSID, IP, MAC, link rate and vendor signal quality.
Disconnected clients become unavailable, not zero signal. A private/rotating MAC
can create a new disabled entity. Absence from Wi-Fi does not prove someone left home.

Signal is reported **as supplied by Aruba**, without claiming dBm or a percentage.
Radio noise fields explicitly supplied as dBm retain that meaning. Link rate
is negotiated Wi-Fi rate, not measured internet throughput.

## Privacy and security

All data stays between your Home Assistant and controller. No analytics or
outbound cloud API. Sessions are closed after each poll. HTTP redirects are not
followed, responses are size bounded, controller errors are sanitized, and TLS
verification cannot silently be disabled. No passwords/session tokens in logs.
Optional client states and SSID attributes may be recorded by Home Assistant;
adjust Recorder exclusions and retention if needed. Diagnostics contain only
counts, firmware version and success state.

## Current limits

- Read-only: no firmware installation, guest disconnect or radio configuration.
- No built-in presence tracking, BLE forwarding or control of Zigbee/Z-Wave.
- Not automatically substituted for an existing working installation.
- If the conductor moves, reauthenticate/reconfigure its AP address.
- If no vendor serial is available, duplicate protection compares the configured
  endpoint; aliases can still identify the same controller twice.
- Public repository upload and catalog checks still need finalizing before public release.

## License and maintainer

MIT License. Maintainer: tunfie. Intended repository:
https://github.com/tunfie/home-assistant-aruba-instant-local

## Development and tests

Tests run against the actual Home Assistant runtime using Python unittest.
Use `python -m unittest discover -s tests -v` with Home Assistant installed.
The tests contain synthetic names, documentation-only addresses and fake credentials.

Read commands: `show aps`, `show clients`, `show network`, `show version`,
`show upgrade`. No arbitrary user command endpoint is exposed.

Vendor reference:
[Aruba Instant REST API guide](https://arubanetworking.hpe.com/techdocs/Aruba-Instant-8.x-Books/812/Aruba-Instant-8.12.0.0-REST-API-Guide.pdf).
This is an independent community integration, not an HPE Aruba product.

## Publishing

See [PUBLISHING.md](PUBLISHING.md). Do not publish private controller outputs or
Home Assistant config files. GitHub checks must pass before catalog submission.
