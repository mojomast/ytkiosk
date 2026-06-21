# Third-Party Licensing

YTKiosk itself is MIT licensed. Release bundles must preserve license notices
for every redistributed component.

## Bundled Or Managed Components

| Component | License | Bundling Plan | Notes |
|---|---|---|---|
| `yt-dlp` | Unlicense | Python package dependency | Use the PyPI package with default extras, not the distro package. |
| `yt-dlp-ejs` and extractor helper packages | Varies by package | Python package dependency via `yt-dlp[default]` | Preserve package metadata/licenses in release artifacts. |
| Deno / Node / QuickJS | Varies by runtime | Optional Linux sidecar in release bundles | Include runtime license and upstream third-party notices when bundled. |
| Python dependencies | Varies | Installed by Python packaging tools | Preserve notices in release artifacts. |

## External System Dependencies

| Component | License | Bundling Plan | Notes |
|---|---|---|---|
| `mpv` | GPLv2-or-later | Not bundled | Installed by the OS package manager to avoid redistributing mpv/FFmpeg/libplacebo stacks. |
| `xset` | MIT/X11-style | Not bundled | Optional best-effort screensaver suppression on X11. |
| `xdg-open` | MIT-style via `xdg-utils` | Not bundled | Optional browser handoff for captive portal flows. |

## Release Rule

Do not publish a binary release that contains Deno, Node, QuickJS, or any other
third-party binary until its license text, upstream version, download URL, and
checksum are recorded in the release notes or generated SBOM.
