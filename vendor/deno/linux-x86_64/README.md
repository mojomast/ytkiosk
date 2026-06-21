# Deno Sidecar Placeholder

Future Linux release bundles can place a pinned `deno` executable here during
release assembly. The source tree intentionally does not commit the large Deno
binary.

Runtime discovery order is:

1. configured path
2. `YTKIOSK_DENO`
3. packaged `ytkiosk/bin/deno`
4. `PATH`
5. `/usr/local/bin/deno`
