#define _DARWIN_C_SOURCE
#include <cups/raster.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

/* Fixture writer uses libcups, independent of the driver's encoder. */
int main(int argc, char **argv) {
    if (argc < 7) return 2;
    unsigned w = (unsigned)atoi(argv[1]), h = (unsigned)atoi(argv[2]);
    unsigned bits = (unsigned)atoi(argv[3]), space = (unsigned)atoi(argv[4]);
    unsigned pages = (unsigned)atoi(argv[5]);
    cups_raster_t *r = cupsRasterOpen(STDOUT_FILENO, atoi(argv[6]) ? CUPS_RASTER_WRITE_COMPRESSED : CUPS_RASTER_WRITE);
    if (!r) return 2;
    cups_page_header2_t hdr;
    memset(&hdr, 0, sizeof(hdr));
    hdr.cupsWidth = w; hdr.cupsHeight = h;
    hdr.cupsBitsPerColor = bits; hdr.cupsBitsPerPixel = bits;
    hdr.cupsBytesPerLine = (w * bits + 7) / 8 + (argc > 8 ? (unsigned)atoi(argv[8]) : 0);
    hdr.cupsColorSpace = (cups_cspace_t)space; hdr.cupsColorOrder = CUPS_ORDER_CHUNKED;
    hdr.cupsNumColors = 1;
    hdr.HWResolution[0] = hdr.HWResolution[1] = argc > 9 ? (unsigned)atoi(argv[9]) : 203;
    hdr.NumCopies = argc > 7 ? (unsigned)atoi(argv[7]) : 1;
    hdr.Duplex = argc > 10 ? (unsigned)atoi(argv[10]) : 0;
    hdr.cupsPageSize[0] = 50 * 72.0f / 25.4f; hdr.cupsPageSize[1] = 25 * 72.0f / 25.4f;
    hdr.PageSize[0] = 142; hdr.PageSize[1] = 71;
    strcpy(hdr.MediaType, "DieCut");
    unsigned char *row = calloc(hdr.cupsBytesPerLine, 1);
    if (!row) return 2;
    for (unsigned p = 0; p < pages; ++p) {
        if (!cupsRasterWriteHeader2(r, &hdr)) {
            fprintf(stderr, "%s\n", cupsRasterErrorString());
            return 3;
        }
        for (unsigned y = 0; y < h; ++y) {
            /* All padding deliberately black: driver must clear unused bits. */
            memset(row, space == CUPS_CSPACE_K ? 255 : 0, hdr.cupsBytesPerLine);
            for (unsigned x = 0; x < w; ++x) {
                int black = p % 3 != 1 && ((x * 17 + y * 13 + p * 7) % 23 < 9);
                unsigned v = space == CUPS_CSPACE_K ? (black ? 255 : 0) : (black ? 0 : 255);
                if (bits == 8) row[x] = (unsigned char)v;
                else if (bits == 1) {
                    unsigned mask = 0x80u >> (x % 8);
                    row[x / 8] = (unsigned char)((row[x / 8] & ~mask) | (v ? mask : 0));
                }
            }
            if (cupsRasterWritePixels(r, row, hdr.cupsBytesPerLine) != hdr.cupsBytesPerLine) return 3;
        }
    }
    free(row); cupsRasterClose(r);
    return 0;
}
