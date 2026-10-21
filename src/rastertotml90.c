/* CUPS 2 raster -> Epson TM-L90, calibrated die-cut stock, monochrome.
 * Protocol provenance and physical-validation limits: docs/tm-l90-driver/evidence.md.
 * No network access and no persistent printer-setting commands in this filter.
 */
#define _POSIX_C_SOURCE 200809L
#define _DARWIN_C_SOURCE
#include <cups/cups.h>
#include <cups/ppd.h>
#include <cups/raster.h>
#include <errno.h>
#include <fcntl.h>
#include <math.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#define MAX_WIDTH 576u
#define MAX_HEIGHT 2400u
#define MAX_PAGES 1000u
#define MAX_JOB_BYTES (256u * 1024u * 1024u)
#define BAND_HEIGHT 128u

static volatile sig_atomic_t cancelled;
static void stop(int sig) { (void)sig; cancelled = 1; }
static int error(const char *s) { fprintf(stderr, "ERROR: TM-L90: %s\n", s); return 1; }

struct input { FILE *file; size_t bytes; int failed; };
static ssize_t raster_read(void *ctx, unsigned char *buf, size_t n) {
    struct input *in = ctx;
    if (!n) return 0;
    if (cancelled) { in->failed = 1; return -1; }
    /* libcups otherwise prefetches compressed data across page boundaries and
     * treats a short final header as clean EOF. Deliver one byte per callback
     * from buffered stdio so consumed bytes distinguish EOF from a short header.
     * This is NOT one read syscall per byte; stdio buffers the underlying file.
     */
    int ch = getc(in->file);
    if (ch == EOF) { if (ferror(in->file)) in->failed = 1; return in->failed ? -1 : 0; }
    if (++in->bytes > MAX_JOB_BYTES) { in->failed = 1; return -1; }
    *buf = (unsigned char)ch;
    return 1;
}

static int put(FILE *f, const void *data, size_t n) {
    return !cancelled && fwrite(data, 1, n, f) == n;
}
#define BYTES(f, ...) put((f), (const unsigned char[]){__VA_ARGS__}, sizeof((const unsigned char[]){__VA_ARGS__}))

/* Sensor positioning uses the printer's previously calibrated layout. */
static int start_label(FILE *out) { return BYTES(out, 0x1c,0x28,0x4c,2,0,67,48); }
static int cut_label(FILE *out) {
    /* APD LabelE4 resource 518/2 + Epson FS(L)66, GS V(A).
     * Cutter shape is a mechanical setting, so do not offer full/partial choices.
     * Epson TRG section 6.3 requires >1 mm of immediate post-cut feed.
     * GS P sets the vertical unit to 1/203 inch; 16 units is about 2 mm.
     */
    return BYTES(out, 0x1c,0x28,0x4c,2,0,66,48, 0x1d,0x56,1, 0x1b,0x4a,16);
}

static int band(FILE *out, const unsigned char *bits, unsigned width, unsigned rows) {
    unsigned n = ((width + 7) / 8) * rows;
    unsigned length = n + 10;
    /* GS ( L function 112 stores one band; function 50 prints and advances it.
     * Width is DOTS, not bytes; padding bits are always white.
     */
    return BYTES(out, 0x1d,0x28,0x4c,length & 255,length >> 8,
                 48,112,48,1,1,49,width & 255,width >> 8,rows & 255,rows >> 8)
        && put(out, bits, n) && BYTES(out, 0x1d,0x28,0x4c,2,0,48,50);
}

static const char *option(int n, cups_option_t *opts, ppd_file_t *ppd,
                          const char *name, const char *fallback) {
    const char *value = cupsGetOption(name, n, opts);
    ppd_choice_t *choice;
    if (value) return value;
    if (ppd && (choice = ppdFindMarkedChoice(ppd, name))) return choice->choice;
    return fallback;
}

static int integer(const char *s, long lo, long hi) {
    char *end;
    long n;
    if (!s || !*s) return 0;
    errno = 0;
    n = strtol(s, &end, 10);
    return !errno && !*end && n >= lo && n <= hi;
}

static int valid_header(const cups_page_header2_t *h) {
    if (!h->cupsWidth || h->cupsWidth > MAX_WIDTH || !h->cupsHeight || h->cupsHeight > MAX_HEIGHT)
        return error("raster dimensions outside 1..576 x 1..2400 dots");
    if (h->HWResolution[0] != 203 || h->HWResolution[1] != 203)
        return error("only 203 x 203 dpi is supported; use this driver's PPD");
    if (h->Duplex || h->Tumble || h->Orientation)
        return error("duplex/unrendered orientation is unsupported; rotate in the renderer");
    if (h->cupsColorOrder != CUPS_ORDER_CHUNKED || h->cupsNumColors != 1 ||
        (h->cupsColorSpace != CUPS_CSPACE_K && h->cupsColorSpace != CUPS_CSPACE_W &&
         h->cupsColorSpace != CUPS_CSPACE_SW) ||
        (h->cupsBitsPerColor != 1 && h->cupsBitsPerColor != 8) ||
        h->cupsBitsPerPixel != h->cupsBitsPerColor)
        return error("expected chunked 1-bit or 8-bit monochrome K/W/SW raster");
    unsigned minimum = (h->cupsWidth * h->cupsBitsPerPixel + 7) / 8;
    if (h->cupsBytesPerLine < minimum || h->cupsBytesPerLine > MAX_WIDTH + 64)
        return error("invalid raster row stride");
    /* The PPD assigns copies/collation to the upstream CUPS renderer. Never
     * multiply argv[4] by pages that the renderer has already duplicated.
     */
    if (h->NumCopies != 1)
        return error("raster NumCopies must be 1; render copies via cupsManualCopies=True");
    if (strcmp(h->MediaType, "DieCut")) return error("only calibrated DieCut media is supported");
    if (!isfinite(h->cupsPageSize[0]) || !isfinite(h->cupsPageSize[1]) ||
        h->cupsPageSize[0] < 107 || h->cupsPageSize[0] > 222 ||
        h->cupsPageSize[1] < 42 || h->cupsPageSize[1] > 851)
        return error("page size must be 38..78 mm wide and 15..300 mm long");
    return 0;
}

int main(int argc, char **argv) {
    struct sigaction sa;
    memset(&sa, 0, sizeof(sa)); sa.sa_handler = stop;
    sigaction(SIGTERM, &sa, NULL); sigaction(SIGINT, &sa, NULL);
    signal(SIGPIPE, SIG_IGN);
    if (argc != 6 && argc != 7) return error("usage: rastertotml90 job-id user title copies options [raster-file]");
    if (!integer(argv[4], 1, 999)) return error("copies must be an integer from 1 to 999");
    cups_option_t *opts = NULL;
    int nopts = cupsParseOptions(argv[5], 0, &opts), result = 1;
    ppd_file_t *ppd = NULL;
    const char *ppdpath = getenv("PPD");
    if (ppdpath && *ppdpath) {
        ppd = ppdOpenFile(ppdpath);
        if (!ppd) { cupsFreeOptions(nopts, opts); return error("cannot open PPD"); }
        ppdMarkDefaults(ppd); cupsMarkOptions(ppd, nopts, opts);
    }
    const char *cut = option(nopts, opts, ppd, "TML90Cut", "None");
    int cutpage = !strcmp(cut, "Page"), cutjob = !strcmp(cut, "Job");
    if (!cutpage && !cutjob && strcmp(cut, "None")) {
        error("TML90Cut must be None, Page, or Job"); goto options_done;
    }
    const char *media = option(nopts, opts, ppd, "MediaType", "DieCut");
    if (strcmp(media, "DieCut")) { error("MediaType must be DieCut"); goto options_done; }
    struct input in = {argc == 7 ? fopen(argv[6], "rb") : stdin, 0, 0};
    if (!in.file) { error("cannot open raster input"); goto options_done; }
    cups_raster_t *raster = cupsRasterOpenIO(raster_read, &in, CUPS_RASTER_READ);
    if (!raster) { error("invalid raster stream"); goto input_done; }
    /* Validate and encode the complete job into an anonymous temporary file
     * before sending any bytes to the backend. A bad later page cannot cause a
     * partly printed job, and working memory remains bounded to one band.
     */
    FILE *out = tmpfile();
    if (!out) { error("cannot create temporary output spool"); goto raster_done; }
    unsigned pages = 0;
    unsigned char row[MAX_WIDTH + 64], bits[((MAX_WIDTH + 7) / 8) * BAND_HEIGHT];
    cups_page_header2_t h;
    if (!BYTES(out, 0x1b,0x40, 0x1d,0x61,0, 0x1d,0x50,203,203, 0x1d,0x4c,0,0)) goto output_error;
    for (;;) {
        size_t before = in.bytes;
        if (!cupsRasterReadHeader2(raster, &h)) {
            if (in.bytes != before) { error("truncated final raster header/trailing data"); goto spool_done; }
            break;
        }
        if (++pages > MAX_PAGES) { error("too many pages (limit 1000)"); goto spool_done; }
        if (valid_header(&h)) goto spool_done;
        if (!start_label(out)) goto output_error;
        unsigned stride = (h.cupsWidth + 7) / 8;
        for (unsigned y = 0; y < h.cupsHeight;) {
            unsigned rows = h.cupsHeight - y;
            if (rows > BAND_HEIGHT) rows = BAND_HEIGHT;
            memset(bits, 0, stride * rows);
            for (unsigned j = 0; j < rows; ++j, ++y) {
                if (cancelled || cupsRasterReadPixels(raster, row, h.cupsBytesPerLine) != h.cupsBytesPerLine) {
                    error("cancelled or truncated raster pixels"); goto spool_done;
                }
                for (unsigned x = 0; x < h.cupsWidth; ++x) {
                    unsigned v = h.cupsBitsPerColor == 1 ?
                        ((row[x / 8] >> (7 - x % 8)) & 1) * 255u : row[x];
                    int black = h.cupsColorSpace == CUPS_CSPACE_K ? v >= 128 : v < 128;
                    if (black) bits[j * stride + x / 8] |= (unsigned char)(0x80u >> (x % 8));
                }
            }
            if (!band(out, bits, h.cupsWidth, rows)) goto output_error;
        }
        if (cutpage && !cut_label(out)) goto output_error;
        long size = ftell(out);
        if (size < 0 || (unsigned long)size > MAX_JOB_BYTES) { error("output spool limit exceeded"); goto spool_done; }
    }
    if (!pages || in.failed || cancelled || (cupsRasterErrorString() && *cupsRasterErrorString())) {
        error("empty, malformed, truncated, or cancelled raster stream"); goto spool_done;
    }
    if (cutjob && !cut_label(out)) goto output_error;
    /* Leave no-cut output at the next print start, including a blank last page. */
    if (!cutpage && !cutjob && !start_label(out)) goto output_error;
    if (fflush(out) || fseek(out, 0, SEEK_SET)) goto output_error;
    size_t got;
    unsigned char buffer[16384];
    while ((got = fread(buffer, 1, sizeof(buffer), out)))
        if (!put(stdout, buffer, got)) goto output_error;
    if (ferror(out) || fflush(stdout) || cancelled) goto output_error;
    for (unsigned p = 1; p <= pages; ++p) fprintf(stderr, "PAGE: %u 1\n", p);
    fprintf(stderr, "INFO: TM-L90: converted %u raster pages; delivery/physical output not confirmed\n", pages);
    result = 0;
    goto spool_done;
output_error:
    error("output write failed or job cancelled");
spool_done:
    fclose(out);
raster_done:
    cupsRasterClose(raster);
input_done:
    if (argc == 7) fclose(in.file);
options_done:
    if (ppd) ppdClose(ppd);
    cupsFreeOptions(nopts, opts);
    return result;
}
