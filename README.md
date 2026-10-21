# Epson TM-L90 Linux CUPS driver

This is a standalone CUPS **2.x** raster driver for the standard Epson TM-L90 on **calibrated, monochrome die-cut labels**. It was built and run on ARM64 Debian 13 in a VM. It has **not been printed on the user's M313C**, installed on the actual Raspberry Pi, or compared with captured Windows print jobs. Treat the first hardware run as acceptance testing, not a production rollout.

The package contains a native C filter, PPD, queue setup script, raster tests, and CUPS/network integration tests. It uses the normal CUPS renderer and socket backend; REA, Java, Ghidra and Windows binaries are **development-only**, not Pi dependencies. This repository contains only the driver, its tests and documentation; CloverAgent and OrderPrinter are separate applications.

## Supported behavior

- CUPS renders PDF, images and text, then this filter converts monochrome raster to Epson `GS ( L` graphics. Resolution is 203 × 203 dpi (the mechanism is nominally 8 dots/mm). The tiny 203-versus-203.2 difference is below one dot on a 50-mm label.
- Default logical page: **50 × 25 mm**, provisional until the stock is measured. Other presets: 50.8 × 25.4, 58 × 40, 70 × 50 mm. Custom logical sizes: width 38–78 mm, length 15–300 mm. These are software bounds, not a statement that every stock size is supported by Epson.
- Imageable margins: 3 mm left/right and 1.5 mm top/bottom. A 50 × 25 mm page therefore renders approximately **352 × 176 printable dots**. Applications must keep important content in this area. The printer's calibrated print-start position must match the imageable top margin; the filter does not rewrite it per job.
- `TML90Cut=None` (default), `Page`, or `Job`. No-cut advances to the next label start after the job. Cut options feed to the layout's cutting position, cut, then immediately feed approximately 2 mm as required by Epson's post-cut guidance. Cutter shape is mechanical, so no software full/partial-cut option is advertised.
- CUPS owns copies, ordering and collation (`cupsManualCopies=True`). The filter emits each supplied raster page once, including blank pages. It deliberately rejects raster `NumCopies != 1` instead of risking multiplication of already expanded copies. Use `lp -n`, not hand-edited raster headers.
- 1-bit and 8-bit chunked monochrome K, W and SW rasters; 8-bit input uses a fixed 128 threshold. The standard PPD requests 1-bit input, leaving halftoning to the CUPS renderer. Noncanonical padded row strides are supported only where the installed CUPS raster library accepts them; hardened CUPS versions require the exact row length implied by width and bit depth. No color, two-color thermal, peel issuing, liner-free, continuous-paper, black-mark-specific or CUPS 3 profile is claimed.
- Bounds: 576 printable dots across, 2400 rows per page, 1000 rendered pages including copies, 256 MiB input/output. Complete jobs are validated and encoded to an anonymous temporary spool before any output reaches the backend. Memory is bounded to one raster band. Temporary disk space is still required.

See [evidence](docs/evidence.md) for Windows-driver findings, exact hashes, protocol sources and limitations. See [TEST_PLAN.md](TEST_PLAN.md) for executed and outstanding checks.

## Install on 64-bit Raspberry Pi OS

Clone this repository onto the Pi and enter its directory. Run the following commands there. First verify the actual OS and architecture:

```sh
cat /etc/os-release
uname -m                 # expected: aarch64
getconf LONG_BIT         # expected: 64
sudo apt-get update
sudo apt-get install build-essential libcups2-dev cups cups-filters ghostscript python3 fonts-dejavu-core
cups-config --version   # must be 2.x
make
make test
sudo make install
sudo systemctl enable --now cups
cupstestppd -W all ppd/epson-tm-l90.ppd
```

Build **on the Pi**; the macOS executable cannot run on Linux. The Makefile uses `cups-config` for the runtime paths (Debian: `/usr/lib/cups/filter/rastertotml90` and `/usr/share/cups/model/cloverhelper/epson-tm-l90.ppd`). Filters are installed mode 0755 and the PPD mode 0644. No existing application code, queue, system default printer, or printer calibration is changed by `make install`. `DESTDIR` is supported for staged packaging.

CUPS 2 PPD drivers are deprecated upstream. Do not use this PPD with CUPS 3; a Printer Application would be a separate integration.

## Prepare media and create the queue

Before printing, read the printer/interface self-test and measure **liner/roll width, actual label width/height, gap and pitch**. Confirm that it is the standard autocutter TM-L90, and that the installed Ethernet board supports raw TCP 9100. UB-E02 documents that endpoint, but the user's board is still unidentified. Do not assume model M313C identifies the board or media layout.

Load the die-cut stock and calibrate it using the printer's documented paper-layout setup or Epson's layout utility. Preserve a known-working Windows layout if one exists. Calibration is a separate persistent setup step: this filter does not guess sensor settings, change memory switches, or write NV layout values. See Epson's [technical reference](https://files.support.epson.com/pdf/pos/bulk/tm-l90_l90_peeler_trg_en_revf.pdf), sections 2.8–2.9 and the die-cut paper/print-area diagrams. Measure a nominal “2 × 1 inch” label before using 50 × 25 mm; 50.8 × 25.4 is a separate preset.

After confirming these settings, substitute the printer's real address and measured logical page:

```sh
sudo sh scripts/configure-queue.sh TML90 192.168.1.50 Custom.50x25mm None
lpstat -v TML90
lpoptions -p TML90 -l
lp -d TML90 -o media=Custom.50x25mm -o TML90Cut=None label.pdf
```

The script refuses to overwrite an existing queue. It configures `socket://HOST:9100/?contimeout=10`, no sharing/banner pages, and `printer-error-policy=stop-printer`. It submits no job. On confirmed autocutter hardware, test cutting, then set it as a default if appropriate:

```sh
lp -d TML90 -n 2 -o media=Custom.50x25mm -o TML90Cut=Page label.pdf
sudo lpadmin -p TML90 -o TML90Cut=Page
# Explicitly update a measured page-size default on an existing queue:
sudo lpadmin -p TML90 -o media-default=Custom.50.8x25.4mm
```

Use `TML90Cut=Job` for one cut after the complete job. For multiple labels without intermediate cuts, labels remain connected on the liner. Do not add `raw` or bypass the PPD: normal PDF/text jobs need rendering. Rotate content in the application/CUPS renderer; the filter expects already oriented raster data.

## CloverAgent

Its existing Linux/macOS path already calls `lp`; configure the deployed application with the queue name and measured media:

```json
"Printing": {
  "EnableDirectPrint": true,
  "PrinterName": "TML90",
  "Media": "Custom.50x25mm",
  "Copies": 1
}
```

Cutting comes from the queue default because CloverAgent does not currently pass a cut option. Its existing `page-left=18` adds a text-layout inset, and its text renderer/font choice is different from the Windows Arial 8 drawing path. The CUPS delivery path was tested with these exact options, but text wrapping, CJK fonts and visual Windows parity are **not established**. Install the required fonts (for example `fonts-noto-cjk` for CJK) and the `en_US.UTF-8` locale expected by the application, then validate real order samples. Long orders can legitimately create multiple pages; the driver must not drop them. The Windows code explicitly sets a 50 × 25 mm page and one copy; the legacy OrderPrinter draws inside that rectangle but does not independently establish printer protocol behavior.

## Errors and retries

```sh
lpstat -p TML90 -l
lpstat -W not-completed -o TML90
journalctl -u cups --since '10 minutes ago'
sudo tail -n 100 /var/log/cups/error_log
```

A successful `lp` call means CUPS accepted the job. A completed socket write means bytes were delivered to the TCP peer, **not that a label printed or cut**. The filter does not implement paper-out/cover-open status polling. CUPS' socket backend owns connection timeouts, side channels and delivery. Some boards hold the connection open; if that behavior is verified, `waiteof=false` can be added to the URI, at the cost of even weaker delivery confirmation.

On the tested Linux backend, refused connections and a reset after 1024 received bytes both returned failure. Some backend/platform versions retry internally before returning (observed on macOS). The queue's stop policy avoids automatically replaying a failed job after a backend reports an error; it cannot retract bytes or detect all buffered-network failures. A connection lost after kernel buffering may still appear successful. Inspect the physical output before resuming or resubmitting: partial and duplicate labels are possible. Cancel a suspect job by its ID before `cupsenable TML90` if replay is unwanted. Restarting a job from CUPS can print it from the beginning.

## Test and remove

```sh
make test
make integration               # cupsfilter + real socket backend; Linux, loopback only
# Full queue integration: use a disposable machine/VM with the driver installed.
sudo python3 tests/integration.py --queue
```

Queue tests create a unique `tml90-test-PID` queue and remove it in a `finally` block. They use no physical printer. To generate the three-page geometric acceptance PDF:

```sh
python3 -c 'import sys; sys.path.insert(0,"tests"); from integration import make_pdf; from pathlib import Path; make_pdf(Path("build/labels.pdf"))'
```

For removal, cancel or complete this queue's jobs, remove only the intended queue, and then remove the two installed driver files. Check that no other queues use the filter before removing it.

```sh
lpstat -W not-completed -o TML90
# cancel TML90-JOB_NUMBER       # only if that specific job should be cancelled
sudo lpadmin -x TML90
sudo make uninstall
```

No CUPS packages, other queues, application settings, or printer calibration are removed. To upgrade, replace the filter with `sudo make install`; an existing queue has its own PPD copy, so update it explicitly with `sudo lpadmin -p TML90 -P ppd/epson-tm-l90.ppd` and reapply its measured media and cut defaults.
