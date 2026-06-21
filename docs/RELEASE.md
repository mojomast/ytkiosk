# Release Notes For Future Bundles

The GUI implementation lives in `src/ytkiosk/legacy.py`; `simple-video-player.py`
is a compatibility launcher. Future release bundles should follow this order:

1. Build and test the Python package with `uv pip install -e .`.
2. Run `python3 test_app.py` and `xvfb-run -a python3 test_integration.py`.
3. Run `ytkiosk-doctor` on the target distro image.
4. Assemble a Linux `onedir` or AppImage bundle that excludes `mpv`.
5. If a JavaScript runtime sidecar is included, prefer a pinned Linux x86_64
   Deno binary at `ytkiosk/bin/deno` in the artifact.
6. Record binary versions, download URLs, checksums, and licenses.
7. Generate or update an SBOM before publishing.

Do not publish a one-file bundle first. A directory bundle is easier to inspect,
debug, and audit while dependency handling is still being stabilized.
