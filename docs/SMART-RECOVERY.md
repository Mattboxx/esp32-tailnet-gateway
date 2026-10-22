# Smart Recovery (experimental dev.4)

Add a host in **Automation → Wake-on-LAN**, then open **Devices & Recovery**.
Extra profiles stay MAC-bound and preserve the original WoL storage layout.
Choose target/scope, a known listening TCP host port, optional service port,
timeout/check limit and optional monitoring/result notification. A NAS with SSH
disabled needs another port; port22 is not a universal reachability test.

**Check now** observes the selected port. **Recover with WoL** prechecks, sends
one bounded WoL burst if needed, waits, then optionally checks the service port.
Initial unknown DNS can still permit the explicitly requested WoL. No target
means an inconclusive result. One active job, MAC cooldown and cancellation
bound the work; jobs never replay on reboot. No power-cut/shutdown/reboot action.

TCP acceptance is not application health. Confirmed local WoL send is not
delivery/power-on; partial UDP-send failures are not separately counted. Finite
SDK DNS retries may delay cancellation. Results/history are boot-local/bounded.

Monitoring/guard/remote commands/notifications start OFF. Guard thresholds are
uncalibrated engineering values. Remote MQTT/ntfy recovery requires the extra
permission and existing integration controls; protect broker/topic ACLs.
ntfy: `recover SAVED_NAME` / `check SAVED_NAME` or saved MAC. HA recovery buttons
use saved MACs. Local recovery does not require MQTT, HA or the managed NAS.
Full security/physical NVS/OTA/resource/fault/browser/soak validation is pending.
