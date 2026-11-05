PREFIX ?= /usr/local
DESTDIR ?=
APPDIR = $(DESTDIR)$(PREFIX)/share/orbitz-workspace

.PHONY: run test install
run:
	./data/orbitz-workspace

test:
	GSETTINGS_BACKEND=memory ORBITZ_LOCALE=pt-BR python3 -m unittest discover -s tests -v

install:
	install -d "$(APPDIR)/app" "$(APPDIR)/i18n" "$(APPDIR)/data"
	cp -R app/. "$(APPDIR)/app/"
	install -m644 i18n/*.py i18n/*.json "$(APPDIR)/i18n/"
	install -Dm755 data/orbitz-workspace "$(DESTDIR)$(PREFIX)/bin/orbitz-workspace"
	install -Dm644 data/io.orbitz.Workspace.desktop "$(DESTDIR)$(PREFIX)/share/applications/io.orbitz.Workspace.desktop"
	install -m644 data/io.orbitz.Workspace.png "$(APPDIR)/data/"
	for size in 16 24 32 48 64 128 256 512; do \
		install -Dm644 "data/icons/hicolor/$${size}x$${size}/apps/io.orbitz.Workspace.png" "$(DESTDIR)$(PREFIX)/share/icons/hicolor/$${size}x$${size}/apps/io.orbitz.Workspace.png"; \
	done
	install -Dm644 data/icons/hicolor/scalable/apps/io.orbitz.Workspace.svg "$(DESTDIR)$(PREFIX)/share/icons/hicolor/scalable/apps/io.orbitz.Workspace.svg"
	install -Dm644 LICENSE "$(APPDIR)/LICENSE"
