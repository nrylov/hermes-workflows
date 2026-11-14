# Alert triage: HighDiskUsage

- Host: web-03
- Severity: page
- Generated: 2026-11-14T04:22:54+00:00

## Diagnostics

`df -h /var` [simulated]
```
Filesystem  Size  Used Avail Use% Mounted on
/dev/sda2    50G   47G  3.0G  94% /var
```

`du -sh /var/log` [simulated]
```
41G	/var/log
```

`ls -lh /var/log/app` [simulated]
```
-rw-r--r-- 1 app app 2.1G Nov 13 20:01 app.log
-rw-r--r-- 1 app app  19G Nov 12 00:00 app.log.1
-rw-r--r-- 1 app app  18G Nov 11 00:00 app.log.2
```

## Hypotheses
- Unrotated application logs: SUPPORTED (matched: app.log.1)
- Core dumps filling disk: not supported

## Proposed remediation (requires human approval, NOT executed)
- Force log rotation: `logrotate -f /etc/logrotate.d/app`
- Compress logs older than 7 days: `find /var/log/app -mtime +7 -exec gzip {} ;`

