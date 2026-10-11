# Visual assets

- `desktop-icon.svg`: original launcher and taskbar icon. Transparent outside its
  blue video tile. PNG exports at 16, 32, 64, 128, and 256 pixels are provided
  with an additional 48-pixel export. `VideoDownloader.png` is the 256-pixel export;
  Qt uses the SVG for window and taskbar icons. Windows ICO and wizard artwork are
  generated from the same vector during packaging.
- `brand-mark.svg`: separate original mark shown inside the application header.
- `actions/*.svg`: monochrome button artwork. The presentation layer renders each
  icon in the foreground color appropriate to its light, blue, or disabled surface.

Both source vectors are drawn for this project. They contain no brand trademarks
and require no network request at runtime. Keep the SVG sources with any future
platform exports so Windows, Linux, and macOS icons can be regenerated cleanly.
