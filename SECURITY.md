# Security

Report vulnerabilities through the repository's private reporting channel when enabled. Do not include private links, cookies, credentials, downloaded media, or personal paths in public issues. If private reporting is unavailable, ask the maintainer to enable it without disclosing the vulnerability.

## Controls

- Pasting a link does not open or inspect it. Inspection requires an explicit click.
- Only public HTTP(S) targets are accepted. Invalid input, known malicious domains, and hosts resolving to local/private addresses are rejected. Native download redirects are checked before connecting; Firefox subrequests and thumbnails also pass through network checks.
- Browser verification uses a disposable profile and the hash-checked, Mozilla-signed uBlock Origin Lite extension, installed before navigation. Personal browser cookies and profiles are never imported. Linux additionally requires Bubblewrap and respects system namespace/AppArmor/SELinux policies.
- Session cookies stay in memory. yt-dlp caches, user configuration, and external plugins are disabled. Logs do not retain source links or browser protocol messages.
- Downloaded files stay in temporary staging until FFprobe identifies an allowed video container with a video stream. HTML, scripts, executables, and playlists disguised as videos are rejected. Cancellation removes staging files before returning home.
- FFmpeg input protocols are restricted to local processing. Downloads use the guarded native HTTP transport, including media fragments. Supported download protocols exclude live streams and external network downloaders.

## Limits

Domain lists and ad blocking cannot identify every malicious site. FFprobe validates format and dimensions, not the absence of malware. Browser and media parser vulnerabilities remain possible. Address checks are not a firewall: a host can change DNS answers between validation and connection, and a configured proxy can resolve a host independently.

Keep the operating system, bundled browser, FFmpeg, and Python dependencies updated. The app cannot guarantee every link is safe, bypass DRM or authentication, or support every website. A retry can help a temporary inspection failure; persistent failures need investigation.

Threat-list updates use a fixed HTTPS source without submitting browsing URLs. The app retains a valid cached list if an update fails; an absent or invalid list blocks requests. Settings store the chosen download folder; source links and proxy credentials are not persisted. Downloaded videos remain until the user removes them. Release archives contain no local settings, browsing profiles, cached media, or test downloads.
