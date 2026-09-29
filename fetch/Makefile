# arctic-fetch-3d — the spinning greeting from fetch.c (see README.md).
#
#   make            build arctic-fetch-3d next to the source
#   make install    into $(LIBEXECDIR), where arctic-fetch looks for it
#
# The RPM builds this in %build with the system cc (gcc is already a BuildRequires);
# a source checkout just needs `make`. Nothing here needs more than libm.

CC ?= cc
# Pinned, deliberately not `?=`. rpmbuild exports its own CFLAGS into %build, so an inherited
# CFLAGS would compile the RPM differently from the fetch-c CI job: the same source would then
# be testable in one place and only fail in the other. A plain `=` beats the environment, so
# this is the single flag set for both. Override on the command line if you need to.
CFLAGS = -O2 -g -pipe -Wall -Werror=format-security -fstack-protector-strong \
         -fno-strict-aliasing -D_FORTIFY_SOURCE=2
LDFLAGS ?=
LDLIBS = -lm
VERSION := $(shell cat VERSION 2>/dev/null || echo 0)
CODENAME ?= Polar Night

LIBEXECDIR ?= /usr/libexec/arctic

UNAME_S := $(shell uname -s)
UNAME_M := $(shell uname -m)
ifeq ($(UNAME_S),Darwin)
  LDLIBS += -framework IOKit -framework CoreFoundation
endif

bin := arctic-fetch-3d

all: $(bin)

$(bin): fetch.c
	$(CC) $(CFLAGS) $(LDFLAGS) -DFETCH_VERSION='"$(VERSION)"' \
	  -DFETCH_CODENAME='"$(CODENAME)"' -DFETCH_ARCH='"$(UNAME_M)"' \
	  -DFETCH_OS='"$(UNAME_S)"' -o $@ $< $(LDLIBS)

install: $(bin)
	install -d $(DESTDIR)$(LIBEXECDIR)
	install -m 755 $(bin) $(DESTDIR)$(LIBEXECDIR)/$(bin)

clean:
	rm -f $(bin)

.PHONY: all install clean
