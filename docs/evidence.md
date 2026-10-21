# TM-L90 implementation evidence — 2026-10-14

## Status and identity

User-confirmed: Epson TM-L90, model M313C, Ethernet, Raspberry Pi, **die-cut labels**, no remote hardware access. Width, height, gap, liner width, Ethernet board, firmware, calibration and Pi OS are still unknown. 50 × 25 mm is an application reference, not a measured media specification. [Epson's declaration](https://epsonemear.a.bigcontent.io/v1/static/e0714-tm-l90-rev_09) links M313C to TM-L90; it does not identify those configuration details.

The driver was originally developed in `CloverHelper/tools/tml90-driver` and extracted into this standalone repository on 2026-10-21. The application references below describe the original integration context; those application sources are not required to build this driver. `CloverAgent/Printing.cs` explicitly requests a 50 × 25 mm Windows page and one copy, and uses `lp` on Linux/macOS. `OrderPrinter/Program.cs` selects `TML90` and draws in a 50 × 25 mm rectangle; its legacy code does not itself pin the physical page. No application layout parity is inferred from these facts.

## Artifact provenance

Downloaded from Epson's public servers; nothing below is redistributed with the source. Hashes identify the inspected bytes, not an independent signature attestation.

| Artifact | Source / role | SHA-256 |
|---|---|---|
| `APD_459aWM_L90LF_e.exe`, 52,865,128 bytes | [Epson download](https://ftp.epson.com/drivers/pos/APD_459aWM_L90LF_e.exe), candidate linked by the [TM-L90 listing](https://epson.com/Support/Point-of-Sale/Label-Printers/Epson-TM-L90-Series-%28Legacy-Product%29/s/SPT_C31C412144?review-filter=Windows+Embedded) | `61fa88b36a493be38a34fcb98f4265f1754d4eb4b1f55ff138efa8bab4779c1a` |
| `apd_455dewm.zip`, 89,598,936 bytes | [Epson APD 4.55d download](https://ftp.epson.com/drivers/pos/apd_455dewm.zip), general TM package | `ed42e6fd277169d88c310777c160f6e072c33639b40c942c7065daab6d15742c` |
| `APD_455dE.exe` | Extracted installer from that ZIP | `be28b017ede2ca32a36fed02e30dd034bebe66d41964bab98d3f4f4e9a5ad139` |
| `INF/TML90/Driver/EAPTM-L9086.INF` | Explicit TM-L90 LabelE4 model registration, DriverVer 05/02/2013, 4.00.55.000 | `dfbbc1281f70f9dd755157dd872669f24c982bc2a178a6dd517344362d336c44` |
| `Driver/EAPd217e.DAT` | LabelE4 module configuration | `7248dbb8a9503f44c17895a5832ddd6454e19643f1e506ca18a6313a1dbfcca3` |
| `Driver/EAPR217e.dll` | LabelE4 model resources | `70148034ecc38dd255c67168d4e312337e15e1123019fd8740ce93cbad589adb` |
| `Driver/EAPDpc0.DLL` | Shared native output module, PE32 x86, 210,432 bytes | `9094dc9f1413c4d59ac4b7441f31f2ae9115c9731be8e0eed2a79b1812b17b72` |

REA `inspect-artifact` identified the 4.59a outer PE but did not unpack its custom payload. 7-Zip exposed an opaque `zlb` overlay. This is **not** evidence that its internal driver supports the target stock, and no native-driver conclusions were taken from it. APD 4.55d extracted successfully with 7-Zip 25.01 and contains the explicitly registered standard TM-L90 LabelE4, separate from Liner-Free and Peeler modules. That is the analyzed reference. It is not confirmed to be the user's installed Windows version. The “E4” name belongs to the APD generation and must not be treated as proof of a hardware 4xx variant.

## REA and Ghidra actually run

REA **6.5.0**, Node **24.15.0**, Ghidra **12.1.4**, and a native ARM64 Temurin JDK **21.0.12.1+1** ran on macOS arm64. Ghidra's release did not include a Mac decompiler; its supplied C++ source was compiled for ARM64 and installed in `Ghidra/Features/Decompiler/os/mac_arm_64/decompile`. The scoped REA doctor returned `healthy: true`, including version, native executable architecture and JDK checks. Other unconfigured providers/client registrations remained irrelevant informational failures. No global Codex MCP registration was required or changed.

Downloads:

- [Ghidra 12.1.4 release](https://github.com/NationalSecurityAgency/ghidra/releases/tag/Ghidra_12.1.4_build): ZIP SHA-256 `ddac49f903da9d5bac833e5cc79395098b9c33cfd3279be5f31bd00387d2d4db`.
- [Adoptium ARM64 macOS JDK 21 endpoint](https://api.adoptium.net/v3/binary/latest/21/ga/mac/aarch64/jdk/hotspot/normal/eclipse): downloaded archive SHA-256 `3623232f33a9c3baadf304480b2535f9a3cba8a58d42ecbb438ba267315d9998`. The endpoint is rolling; future bytes will differ.

The native decompiler build overrides the upstream Makefile's x86 default:

```sh
cd "$GHIDRA_INSTALL_DIR/Ghidra/Features/Decompiler/src/decompile/cpp"
# Use a fresh extracted source tree when changing architectures.
make -j4 ghidra_opt ARCH_TYPE='-arch arm64' ADDITIONAL_FLAGS='-mmacosx-version-min=11.0 -w'
mkdir -p "$GHIDRA_INSTALL_DIR/Ghidra/Features/Decompiler/os/mac_arm_64"
install -m 755 ghidra_opt "$GHIDRA_INSTALL_DIR/Ghidra/Features/Decompiler/os/mac_arm_64/decompile"
```

Set `GHIDRA_INSTALL_DIR` and `JAVA_HOME` to those local installations. REA's [installation documentation](https://github.com/morluto/rea/blob/main/docs/installation.md) describes the provider contract. Reproduce the scoped analysis outside the repository:

```sh
npx --yes rea-agents@6.5.0 doctor --provider ghidra --format json
npx --yes rea-agents@6.5.0 inspect-artifact "$SCRATCH/APD_455dE.exe" --format json
npx --yes rea-agents@6.5.0 inspect-pe-resources "$DRIVER/EAPR217e.dll" --format json
npx --yes rea-agents@6.5.0 decompile "$DRIVER/EAPDpc0.DLL" NextPage --provider ghidra --format json
npx --yes rea-agents@6.5.0 decompile "$DRIVER/EAPDpc0.DLL" BandOut --provider ghidra --format json
npx --yes rea-agents@6.5.0 decompile "$DRIVER/EAPDpc0.DLL" 0x00407a90 --provider ghidra --format json
npx --yes rea-agents@6.5.0 decompile "$DRIVER/EAPDpc0.DLL" 0x00427e80 --provider ghidra --format json
npx --yes rea-agents@6.5.0 decompile "$DRIVER/EAPDpc0.DLL" 0x00429ac0 --provider ghidra --format json
npx --yes rea-agents@6.5.0 decompile "$DRIVER/EAPDpc0.DLL" 0x00429ce0 --provider ghidra --format json
npx --yes rea-agents@6.5.0 decompile "$DRIVER/EAPDpc0.DLL" 0x00429f80 --provider ghidra --format json
```

Here `SCRATCH` is your temporary analysis directory and `DRIVER` the extracted `Driver` directory. The session used `/private/tmp/tml90-analysis`; binaries, raw resources, decompilation JSON and VM scratch remain there and may disappear on cleanup/reboot. [analysis-manifest.json](analysis-manifest.json) retains operation identities and hashes without bundling vendor content. Analysis addresses refer to this exact PE image and its image base, not source line numbers.

## Verified static findings and their limits

| Finding | Evidence | What it establishes |
|---|---|---|
| Standard LabelE4 selects `EAPR217e` and shared `EAPDpc0` | Extracted INF and DAT | Correct model-specific resource/output modules for this reference package |
| A label resource contains `1c 28 4c 02 00 42 30 1d 56 01` | REA PE-resource inventory; independently extracted resource type **518**, ID **2**, offset **0x1f7** | Presence of feed-to-cut-position followed by cutter actuation in the model's command data. It does **not** prove a particular Windows job selects it. |
| `BandOut` (0x00406320) prepares a band and queues it through 0x004080c0 | REA/Ghidra decompilation | Raster data is buffered and padded/aligned in the Windows path |
| 0x00407a90 flushes a pending band, iterating height chunks, with separate one-/multi-plane paths | REA/Ghidra, reached from both `NextPage` and band submission | Banded raster output; Windows band sizes and trimming are configuration dependent |
| 0x00427e80 selects encoder implementations using configuration bytes | REA/Ghidra | There are multiple Windows raster protocols; no single unconditional byte stream is inferred |
| 0x00429ac0 constructs RTTI-identified `PosBitImageCmdGSL112` | REA/Ghidra constructor/vtable evidence | Windows output module has a `GS ( L` function 112 encoder, the same documented command family chosen for Linux |
| Its 0x00429b70 method allocates/copies `(aligned_width >> 3) * height`, with scaling/plane conditions | REA/Ghidra | One-bit packed raster storage in that implementation; not proof of the user's active settings |
| 0x00429ce0 constructs `GS 8 L` with function 112, monochrome tone, scale fields, color 49 and dot width/height; its length includes ten parameter bytes | REA/Ghidra, 17-byte header callback followed by image callback | Concrete graphics-header fields in one Windows branch. Linux uses the documented equivalent short-length `GS ( L` form for its smaller bands. Windows has additional plane/width adjustments. |
| 0x00429f80 invokes its store helper, then sends `1d 28 4c 02 00 30 32` | REA/Ghidra, seven-byte output callback | Function 50 follows stored graphics in this encoder. Blank data may instead take a feed-only optimization; Linux intentionally emits blank raster rows. |
| `NextPage` (0x00405f90) flushes remaining image data before page completion; helper 0x00423d70 emits configured bytes via a callback | REA/Ghidra | Explicit image/page-finalization ordering; callback/state provenance remains partly indirect |

The module also contains format templates for legacy `GS v 0`, positioning and cutting. A REA xref query against the legacy raster template returned no direct references; that absence does not prove the path is unused. A provider-neutral `inspect-binary-layout` attempt was unavailable on this host and was not substituted for native evidence. No Windows installer or driver code was executed. Ghidra output is recovered pseudocode with uncertain types and indirect calls, not original source. The Linux filter is a new implementation of documented commands, not a port of proprietary source.

## Protocol decisions verified against Epson documentation

The [TM-L90 command list](https://download4.epson.biz/sec_pubs/pos/reference_en/escpos/tml90.html) includes these commands for the standard family; it is distinct from the LFC command list.

| Linux behavior | Primary reference / constraint |
|---|---|
| Store bounded, packed monochrome raster bands; then print each band | [`GS ( L` function 112](https://download4.epson.biz/sec_pubs/pos/reference_en/escpos/gs_lparen_cl_fn112.html) and [function 50](https://download4.epson.biz/sec_pubs/pos/reference_en/escpos/gs_lparen_cl_fn50.html). Width is dots; payload uses rounded-up byte rows. 128-row bands stay below the listed TM-L90 buffer limits. |
| Position at next start without skipping an already aligned label | [`FS ( L` function 67](https://download4.epson.biz/sec_pubs/pos/reference_en/escpos/fs_lparen_cl_fn67.html), mode 48. Relies on the stored paper layout. |
| Position and actuate cutter | [`FS ( L` function 66](https://download4.epson.biz/sec_pubs/pos/reference_en/escpos/fs_lparen_cl_fn66.html), mode 48, and [`GS V`](https://download4.epson.biz/sec_pubs/pos/reference_en/escpos/gs_cv.html), function A, corroborated by LabelE4 resource bytes. Generic function-66 notes discuss black-mark media; the model's layout origin and actual die-cut behavior still require hardware acceptance. The no-cut default avoids silently assuming cutter configuration. |
| Feed immediately after cutting; respect mechanism bounds and label margins | [TM-L90 technical reference](https://files.support.epson.com/pdf/pos/bulk/tm-l90_l90_peeler_trg_en_revf.pdf), §6.3, specifications and printable-area diagrams. Linux selects a conservative imageable rectangle and does not use reverse-feed cut function D. |
| CUPS transports stdout to the printer | [UB-E02 reference](https://download4.epson.biz/sec_pubs/bs/pdf/ube02trm_e_1.pdf) documents raw TCP 9100, conditional on the installed board. The filter has no socket code. |
| Renderer expands copies | [CUPS `cupsManualCopies`](https://openprinting.github.io/cups/doc/spec-ppd.html#cupsManualCopies), verified through actual collated/uncollated Linux queue jobs. |

Initialization resets volatile print state and disables unsolicited ASB. No job writes paper-layout, memory-switch or NV-setting commands. Pixel thresholding, 128-row band choice, full-job validation/spooling, resource limits and conservative PPD margins are Linux implementation decisions, not claims about Windows defaults.

## What remains unverified

No Windows reference `.prn`/packet capture, actual Pi OS build, printer self-test, physical label, sensor position, cut location, barcode scan or prolonged run was available. Native ARM64 Debian tests establish Linux ARM execution, **not** Raspberry Pi hardware validation. Do not claim byte identity, complete Windows feature parity, exact text layout, or physical print success from these results. Capture the Windows driver/version/settings and compare decoded image content plus feed/cut events using the acceptance plan before making those claims.
