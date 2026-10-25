# Documentation — ESP32 Tailnet Gateway

User guides for the current firmware, the technical reference and the project
records. The [website](https://mattboxx.github.io/esp32-tailnet-gateway/)
presents the same guides for reading online, and the
[wiki](https://github.com/Mattboxx/esp32-tailnet-gateway/wiki) summarizes them
by task.

## Start here

- [Getting started](GETTING-STARTED.md): install, first boot and first rule.
- [First-boot setup](FIRST-BOOT-SETUP.md): pairing, Wi-Fi test and where to
  find the gateway afterwards.
- [Firmware updates](UPDATES.md): Web UI, GitHub updater and USB, keeping settings.
- [Hardware](HARDWARE.md): supported ESP32-S3 boards, power and wiring.
- [Troubleshooting](TROUBLESHOOTING.md)

## Guides by role

| Role | Guide |
|---|---|
| Reach one Tailnet service from LAN devices | [Service Gateway](SERVICE-GATEWAY.md) |
| Reach this LAN from the tailnet | [Subnet router](SUBNET-ROUTER.md) |
| Route Internet traffic through the gateway | [Exit node](EXIT-NODE.md) |
| Self-hosted control server | [Headscale](HEADSCALE.md) |
| Wake and check a NAS or PC | [NAS recovery](NAS-RECOVERY.md), [Smart Recovery](SMART-RECOVERY.md) |
| Monitoring | [Network health](NETWORK-HEALTH.md) |
| Automation | [MQTT](MQTT.md), [Home Assistant](HOME-ASSISTANT.md), [ntfy](NTFY.md) |
| Wired uplink (experimental W5500) | [Ethernet](ETHERNET.md) |
| Mobile uplink with a SIM (experimental, 3.0) | [Cellular](CELLULAR.md) |
| From 2.x to 3.0 (settings kept) | [Migration](MIGRATION-3.0.md) |
| Dynamic DNS (DuckDNS, Cloudflare, update URL) | [Dynamic DNS](DDNS.md) |
| Telegram and email notifications | [Notifications](NOTIFICATIONS.md) |
| Web UI languages | [Languages](I18N.md) |
| Settings | [Configuration](CONFIGURATION.md), [Backup and restore](BACKUP-RESTORE.md) |

The [guide coverage table](GUIDES.md) maps every guide subject to its document.

## Security

- [Security policy and model](../SECURITY.md)
- [Tailnet authorization](TAILNET-AUTHORIZATION.md)

## Technical reference

- [Architecture](ARCHITECTURE.md) and [architecture decisions](ARCHITECTURE-DECISIONS.md)
- [NVS keys](NVS-KEYS.md), [ntfy transport](NTFY-TRANSPORT.md), [translations](I18N.md)
- [Testing](TESTING.md) and the [release quality policy](QUALITY-GATE.md)
- [Website maintenance](WEBSITE.md)

## Project and maintainers

- [Roadmap](ROADMAP.md) and the authoritative [development roadmap](DEVELOPMENT-ROADMAP.md)
- [Feature implementation matrix](FEATURE-IMPLEMENTATION-MATRIX.md) and
  [validation status](VALIDATION-STATUS.md)
- [Release availability](PRESENTATION-STATUS.md) and the
  [repository rename](MIGRATION-RENAME.md)
- Contributor and agent instructions: [AGENTS.md](../AGENTS.md),
  [goals](../GOALS.md), [master mandate](MASTER-DEVELOPMENT-PROMPT.md),
  [next steps](NEXT-STEPS-FOR-AGENT.md), [contributing](../CONTRIBUTING.md)

## Releases and history

- [Changelog](../CHANGELOG.md) for every version, newest first.
- [releases/](releases/): detailed notes of earlier 1.x releases.
- [upstream/](upstream/): how each upstream version was merged.
- [archive/](archive/): superseded plans, handoffs and records, kept for history.
- [launch/](launch/): announcement texts.
