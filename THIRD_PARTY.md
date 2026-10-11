# Third-party components

The application source is MIT-licensed. Dependencies and separately bundled programs retain their own licenses; release packages include their notices under `licenses/` and component directories.

| Component | License | Source |
| --- | --- | --- |
| Python | PSF | [python.org](https://www.python.org/) |
| Qt / PySide6 | LGPL-3.0 / GPL alternatives and component notices | [Qt](https://code.qt.io/) |
| yt-dlp | Unlicense with third-party notices | [yt-dlp](https://github.com/yt-dlp/yt-dlp) |
| curl-cffi | MIT with bundled curl notices | [curl-cffi](https://github.com/lexiforest/curl_cffi) |
| Firefox | MPL-2.0 and component notices | [Mozilla source](https://hg.mozilla.org/mozilla-release/) |
| FFmpeg Windows essentials build | GPL-3.0-or-later | [Gyan builds](https://www.gyan.dev/ffmpeg/builds/), [exact upstream revision](https://github.com/FFmpeg/FFmpeg/commit/946fcce07b) |
| Node.js | MIT with component notices | [Node.js](https://github.com/nodejs/node) |
| uBlock Origin Lite | GPL-3.0 | [uBOL source](https://github.com/uBlockOrigin/uBOL-home) |
| HaGeZi Threat Intelligence Feeds Mini | GPL-3.0 | [HaGeZi lists](https://github.com/hagezi/dns-blocklists) |

The Mozilla-signed uBlock Lite XPI is a separate extension. Its expected SHA-256 is checked before use. HaGeZi's original list headers are preserved; its GPL text is included beside the list. FFmpeg and Node run as separate command-line tools. Linux uses the distribution's FFmpeg and Bubblewrap packages.

Qt libraries remain replaceable in the Windows `_internal` folder. Users may replace compatible libraries and modify this MIT application; no restrictions on debugging such modifications are imposed by the project. Consult each component's notices and source links for its own terms.
