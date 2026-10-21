# TM-L90 validation

## Standalone extraction check — 2026-10-21

The standalone repository was built from source on macOS arm64 with the system CUPS library. `make test` passed all 13 test methods after the portability change below. The driver C source, PPD and queue script are unchanged from the original package; README links now resolve inside this repository. The included GitHub Actions workflow is configured to run the Linux build, PPD validation and renderer/socket integration tests on Ubuntu 24.04. Hardware acceptance below remains outstanding.

Ubuntu CI exposed stricter CUPS raster header validation: padded row lengths are rejected before the fixture writer emits pixels. Canonical raster cases now always run across all widths, polarities and compression modes. A separate padded-row test runs where the installed CUPS library supports padding and explicitly skips only when its writer reports a row-length/width mismatch. Fixture failures retain the CUPS diagnostic; other errors still fail the suite. See [CUPS row-length validation](https://github.com/OpenPrinting/cups/blob/master/cups/raster-stream.c).

## Executed 2026-10-14

| Environment | Result |
|---|---|
| macOS arm64, system libcups, Apple clang | Strict C11 build; 12 unittest methods passed, with parameterized raster cases. PPD validation passed (expected missing-system-filter warning because no host installation was made). |
| Debian 13 ARM64 in Lima/VZ VM | Native GCC build and execution, CUPS 2.4.10, cups-filters 1.28.17. 12 test methods passed. `file` identified Linux ARM aarch64 ELF with `/lib/ld-linux-aarch64.so.1`. |
| Same ARM64 Linux, ASan + UBSan | 12 test methods passed with no reported sanitizer errors. |
| Installed Linux driver | `make install`, PPD validation, queue configuration/default inspection, staged install/uninstall and preservation of an unrelated sentinel passed. No physical destination was used. |
| Linux CUPS integration | See cases below. Completed successfully with the actual renderer, scheduler and socket backend, using a loopback TCP sink. |
| macOS integration subset | PDF geometry and exact socket payload passed. The refused-connection backend stayed in retry rather than returning within 15 seconds; test process timed out. Linux is the supported integration target; do not report the complete macOS integration suite as passing. |

Raw test/analysis logs were retained under `/private/tmp/tml90-analysis`, outside source control. Commands and fixtures are reproducible from this package.

## Automated cases

`make test` checks:

1. Independent decode of encoded pixel content at widths 1, 7, 8, 9, 351, 352, 575 and 576 dots; 259-row images cross two band boundaries. It compares every pixel, not just byte counts.
2. 1-/8-bit K/W/SW polarity, compressed and uncompressed CUPS raster, padded source strides where the installed CUPS library supports them, and deliberately dirty trailing bits.
3. Three-page output including a completely blank middle page; preserved image heights and page order; None/Page/Job cut sequencing and immediate post-cut feed.
4. Copies ownership: already expanded raster is never multiplied by the filter's `argv[4]`; unsupported raster copy counts fail explicitly. Actual copy expansion is separately tested through CUPS.
5. File versus stdin equivalence; invalid options, copies, resolution, colorspace, bit depth, dimensions, duplex and missing PPD.
6. Empty/wrong-format input, truncated headers/pixels and trailing partial headers on both raster encodings. Failure emits zero printer bytes, including when a prior page was valid. These tests exposed libcups treating partial final headers as EOF; the filter now tracks exact consumed bytes through a buffered input callback.
7. Cancellation while blocked on input emits no bytes; exceeding the page limit fails atomically. Broken output pipe returns failure; stdout contains only printer data, diagnostics/accounting go to stderr.
8. Staged installation permissions/paths, uninstall scope, and invalid queue arguments rejected before system changes.

`make integration` runs on Linux with CUPS installed:

- PDF -> CUPS raster -> driver: 50 × 25 mm page, approximately 352 × 176 printable dots, measured 10-mm and 5-mm black squares at known coordinates, plus a blank page.
- Other PPD presets and minimum/maximum custom dimensions pass through the real renderer.
- Real CUPS socket backend delivers exactly the encoded bytes to a simulated printer.
- Refused connection returns failure; forced reset after 1024 bytes of a large stream returns failure. The large stream intentionally exceeds TCP buffering to make the failure observable.

`sudo python3 tests/integration.py --queue`, after installation in a **disposable Linux VM**, additionally verifies:

- `lp` -> `cupsd` -> installed PDF/filter chain -> socket -> TCP sink.
- Three pages × two copies, both collated (ABCABC) and uncollated (AABBCC), preserving the blank page.
- CloverAgent's exact UTF-8 text/plain, margin, fit-to-page and two-copy submission options.
- Refused delivery leaves the job pending and disables the queue under `stop-printer`; test cleanup cancels only its jobs and removes only its unique queue.

No simulated sink interprets sensor state, cutter mechanics, head heat, firmware flow control or physical registration. Successful decoding is not evidence of those behaviors.

## Reproduce sanitizer checks

```sh
make clean
make test CFLAGS='-O1 -g -std=c11 -Wall -Wextra -Wpedantic -Werror -Wno-deprecated-declarations -fsanitize=address,undefined -fno-omit-frame-pointer' LDFLAGS='-fsanitize=address,undefined'
make clean
make
```

Use the normal build for installation. To reproduce the Linux environment without the printer, use an ARM64 Debian 13 VM with the packages listed in README, copy this directory inside it, and run the build/install/tests there. The implementation session used Lima 2.2.1 with the Debian ARM64 genericcloud image dated 2026-10-01; this is not a claim about the user's Pi OS.

## Required hardware acceptance — outstanding

1. Record Pi model, `/etc/os-release`, `uname -m`, `getconf LONG_BIT`, CUPS version, printer firmware/self-test, full product variant and Ethernet board. Confirm raw TCP 9100 on that board.
2. Measure liner width, label width/height, gap and pitch. Confirm the label sensor and calibrated layout, print-start offset and cut position. Choose the corresponding logical page size; do not silently equate 50 × 25 mm with 2 × 1 inch stock. Keep the original Windows configuration available for comparison.
3. Build/install on the Pi. Start with one no-cut PDF containing marks inside the imageable area. Measure the square, top/left position and usable margins; confirm there is no clipping or skipped label. Check first-job positioning after power-up and after opening the cover.
4. Print three labels with a blank middle label, then two copies in each collation order. Confirm exact label counts, start positions and that none of the printer's automatic behavior duplicates feed operations.
5. On confirmed autocutter hardware, test Page and Job cuts. Cuts must lie in liner gaps, never through adhesive. Verify post-cut feed, next-job registration and no accumulating drift over at least 100 labels. Test no-cut issuing separately.
6. Print representative CloverAgent orders including long lines and required Unicode scripts. Verify font availability, wrapping, clipping and number of labels. Print production barcode/image fixtures and scan barcodes. These may differ visually from Windows despite correct raster transport.
7. Capture Windows spool/printer bytes for the same physical stock and settings. Compare decoded bitmap geometry/content and semantic positioning/cut events; retain the driver version and settings. Byte equality is not required, but “Windows parity” needs this evidence.
8. Test paper-out, cover-open, unplug/reconnect, reset and partial-delivery recovery. Inspect output before retrying a job; record duplicate/partial-label behavior and operator recovery. `lp` acceptance and backend completion alone are insufficient.
9. Remove only the test queue/driver after testing if appropriate; confirm unrelated queues/application configuration remain intact.

Record observed results, measurements and failures before enabling unattended CloverAgent production printing. None of these physical steps has been marked passed.
