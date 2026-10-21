CC ?= cc
CUPS_CONFIG ?= cups-config
CPPFLAGS += $(shell $(CUPS_CONFIG) --cflags)
CFLAGS ?= -O2 -g
CFLAGS += -std=c11 -Wall -Wextra -Wpedantic -Werror -Wno-deprecated-declarations
LDLIBS += $(shell $(CUPS_CONFIG) --libs) -lm
SERVERBIN ?= $(shell $(CUPS_CONFIG) --serverbin)
DATADIR ?= $(shell $(CUPS_CONFIG) --datadir)

.PHONY: all test integration install uninstall clean
all: build/rastertotml90 build/raster-fixture
build:
	mkdir -p $@
build/rastertotml90: src/rastertotml90.c | build
	$(CC) $(CPPFLAGS) $(CFLAGS) $(LDFLAGS) $< $(LDLIBS) -o $@
build/raster-fixture: tests/raster_fixture.c | build
	$(CC) $(CPPFLAGS) $(CFLAGS) $(LDFLAGS) $< $(LDLIBS) -o $@
test: all
	python3 -m unittest discover -s tests -p 'test_*.py' -v
integration: all
	python3 tests/integration.py
install: build/rastertotml90
	install -d "$(DESTDIR)$(SERVERBIN)/filter" "$(DESTDIR)$(DATADIR)/model/cloverhelper"
	install -m 755 build/rastertotml90 "$(DESTDIR)$(SERVERBIN)/filter/rastertotml90"
	install -m 644 ppd/epson-tm-l90.ppd "$(DESTDIR)$(DATADIR)/model/cloverhelper/epson-tm-l90.ppd"
# Remove the queue explicitly before this target. No other files/queues are touched.
uninstall:
	rm -f "$(DESTDIR)$(SERVERBIN)/filter/rastertotml90" "$(DESTDIR)$(DATADIR)/model/cloverhelper/epson-tm-l90.ppd"
clean:
	rm -f build/rastertotml90 build/raster-fixture
