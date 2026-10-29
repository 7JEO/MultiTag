#!/usr/bin/env bash
# Installs MultiTag into the KDE application launcher (per-user, no root needed).
set -e
here="$(cd "$(dirname "$0")" && pwd)"
app="$HOME/.local/share/multitag"
icons="$HOME/.local/share/icons/hicolor/scalable/apps"
# remove the old StreamSync install, if any
rm -rf "$HOME/.local/share/streamsync" "$HOME/.local/share/applications/streamsync.desktop" "$HOME/.local/share/icons/hicolor/scalable/apps/streamsync.svg"
mkdir -p "$app" "$icons" "$HOME/.local/share/applications"

install -m755 "$here/multitag.py" "$app/multitag.py"

cat > "$app/multitag.svg" <<'SVG'
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128">
  <rect width="128" height="128" rx="28" fill="#1f1f2e"/>
  <g stroke="#b8b8c8" stroke-width="5" stroke-linecap="round" fill="none">
    <path d="M44 64 L84 32"/><path d="M44 64 L84 64"/><path d="M44 64 L84 96"/>
  </g>
  <circle cx="32" cy="64" r="13" fill="#ffffff"/>
  <circle cx="98" cy="32" r="11" fill="#9146FF"/>
  <circle cx="98" cy="64" r="11" fill="#53FC18"/>
  <circle cx="98" cy="96" r="11" fill="#FF0033"/>
</svg>
SVG

cat > "$HOME/.local/share/applications/multitag.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=MultiTag
GenericName=Multistream manager
Comment=Update stream title, category and tags on Twitch, Kick and YouTube
Exec=python3 $app/multitag.py
Icon=$app/multitag.svg
Terminal=false
Categories=Network;Utility;
Keywords=stream;twitch;kick;youtube;title;category;
StartupWMClass=multitag
DESKTOP

cp "$app/multitag.svg" "$icons/multitag.svg"

update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true
gtk-update-icon-cache -f -t "$HOME/.local/share/icons/hicolor" 2>/dev/null || true
(kbuildsycoca6 --noincremental || kbuildsycoca5 --noincremental) >/dev/null 2>&1 || true
echo "Installed. Search for MultiTag in the application launcher."
echo "If the icon is still missing, log out and back in (or run: kquitapp6 plasmashell && kstart plasmashell)."
