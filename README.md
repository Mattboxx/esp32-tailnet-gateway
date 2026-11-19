# This project moved to RecoveryGateway

**ESP32 Tailnet Gateway is now RecoveryGateway — Mattboxx Edition.**

- Source, issues, discussions and releases: <https://github.com/Mattboxx/RecoveryGateway>
- Website and browser installer: <https://mattboxx.github.io/RecoveryGateway/>

Please open issues and pull requests in the new repository.

## Why this repository exists

Gateways running firmware **3.0.27 or older** look for updates only under
`Mattboxx/esp32-tailnet-gateway`. This repository keeps that name so those
gateways can still find one update: the **transition release 3.0.28**, the same
image published in RecoveryGateway. From 3.0.28 the updater looks in
`Mattboxx/RecoveryGateway`, so every later update comes from there.

- Update from the web interface as usual: **System → Firmware → Check for
  updates**, then install 3.0.28. Settings are kept.
- This repository only receives a new release when a newer transition image is
  needed. It has no source code: the source of every release, including 3.0.28,
  is in [Mattboxx/RecoveryGateway](https://github.com/Mattboxx/RecoveryGateway)
  under the same tag.
- Its website only redirects old links
  (`mattboxx.github.io/esp32-tailnet-gateway/...`) to the same page of the new
  website.

The firmware is licensed under GPL-3.0 (see [LICENSE](LICENSE)); the release
files include the licence notices of every component.
