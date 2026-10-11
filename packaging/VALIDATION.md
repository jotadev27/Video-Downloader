# v1.0 verification

Verified on the Windows x64 build host using generated fixtures only:

- 105 regression tests passed; two POSIX fake-executable tests were skipped.
- Ruff import/syntax/undefined-name checks passed; `pip check` found no broken dependencies.
- Package metadata and the application version both report 1.0.0.
- The frozen app starts and closes cleanly. Native caption and taskbar icon handles are present.
- Offline diagnostics pass Firefox/uBlock inspection through redirects and iframes, temporary cookies, encrypted HLS, video-container checks, a file over 2 GB, synthetic threat filtering, and temporary-file removal.
- Windows cleanup regressions cover owned browser process trees, extension paths longer than MAX_PATH, and briefly locked files.
- Official runtime downloads were verified before use. Linux Firefox/Node archives match Mozilla/Node checksums. The signed Inno Setup compiler builds the English wizard with both generated artwork images.
- Linux installer shell syntax passes with the installed Git Bash. Linux binaries retain their original Unix executable permissions in the release tarball.
- Public-source audit checks generated/private file exclusions, personal absolute paths, common secret markers, and the uBlock XPI hash. Source test links are synthetic; no personal media or browser profile was used.
- Exactly five release files are present. SHA-256 checksums, ZIP CRCs, Windows/Linux x64 headers, Windows icon resources, Unix executable permissions, and archive exclusions passed verification.

The Linux installer has not been executed on Ubuntu, Manjaro, Arch, or Fedora on this Windows host. Target-distribution installation and end-user download compatibility remain for user testing. These checks are not a complete vulnerability scan or a guarantee that arbitrary media is harmless.
