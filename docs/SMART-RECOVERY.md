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

Monitoring, the guard, remote commands and notifications start off. Guard
thresholds are engineering defaults. Under **Automation → Notifications**,
choose the command mode separately for ntfy and Telegram. The verified
recovery mode adds `recover SAVED_NAME` and `check SAVED_NAME` (or a saved MAC)
to the basic commands. The info, destination and polling options still apply.
Under **Automation → Home Assistant**, the MQTT recovery switch permits the
MQTT recovery command for saved MACs. Protect your broker and topic permissions.
Local recovery works independently of these integrations.
Full security/physical NVS/OTA/resource/fault/browser/soak validation is pending.
