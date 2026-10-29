[MultiTag Installation Guide.md](https://github.com/user-attachments/files/34130318/MultiTag.Installation.Guide.md)
# MultiTag Installation Guide

*For Arch Linux with KDE Plasma. MultiTag updates your stream title, category and tags on Twitch, Kick and YouTube from one window.*

## 1. What you need

- Arch Linux (or another distro with Python 3 and Qt 6)
- A web browser, used for the one-time login to each platform
- Accounts on the platforms you want to use

Install the dependencies:

```
sudo pacman -S python python-pyqt6 python-requests
```

## 2. Get the files

Put `multitag.py` and `install.sh` in the same folder, for example `~/Downloads/multitag/`.

## 3. Install

From that folder, run:

```
bash install.sh
```

This needs no root. It does the following:

- Copies the app and its icon to `~/.local/share/multitag/`
- Adds a **MultiTag** entry to the application launcher
- Removes any old StreamSync install
- On first launch, moves your old settings from `~/.config/streamsync` to `~/.config/multitag`, so existing logins carry over

Search for **MultiTag** in the launcher. If it doesn't appear, or the icon is missing, log out and back in, or run:

```
kbuildsycoca6 --noincremental && kquitapp6 plasmashell && kstart plasmashell
```

## 4. Register an app on each platform

MultiTag talks to each platform through its official API, so you create a free developer app on each one and paste its credentials into MultiTag. You only need to set up the platforms you use.

### Twitch

1. Go to dev.twitch.tv/console and register a new application.
2. Set the **Client Type** to **Public**.
3. Use `http://localhost` as the OAuth redirect URL.
4. Copy the **Client ID**. No secret is needed.

### Kick

1. Create an app in your Kick developer settings.
2. Set the redirect URI to exactly `http://localhost:8976/callback`.
3. Copy the **Client ID** and **Client Secret**.

### YouTube

The YouTube Data API is free (a daily quota applies) and does not need a billing account.

1. Go to console.cloud.google.com and create a project. If it offers a free trial or asks for a card, dismiss it.
2. Open **APIs & Services → Library**, search for **YouTube Data API v3** and click **Enable**.
3. Open the **OAuth consent screen**, choose **External**, and add your own Google account as a test user.
4. Open **Credentials → Create credentials → OAuth client ID**, choose **Desktop app**, and copy the **Client ID** and **Client Secret**.

While the consent screen is in **Testing**, Google expires logins after 7 days, so MultiTag will ask you to log in again about once a week. Publishing the app to **Production** avoids this. For personal use that only shows an "unverified app" warning that you can click through.

## 5. Enter your credentials

1. Open MultiTag and click **Settings**.
2. Fill in the IDs and secrets from the previous step.
3. Leave **Update Url** blank. MultiTag already checks its own GitHub repo for updates (see section 8).
4. Click **Save**.

Credentials and logins are stored in `~/.config/multitag/` with owner-only permissions. They are not encrypted.

## 6. First login

Press **Apply to selected** once. For each platform that isn't logged in yet, your browser opens so you can approve access. Twitch shows a short code to confirm. After that, logins refresh automatically.

The log at the bottom shows `OK` or `ERR` for each platform, with the error message if something fails.

## 7. Everyday use

- **Current info:** when you open MultiTag, it loads the title, category and tags already set on your logged-in platforms and fills the fields. The log shows each platform's values. Use **Refresh** to reload them.
- **Category:** start typing and a dropdown suggests matching categories from Twitch and Kick. YouTube has no category in its API, so it is skipped there.
- **Tags:** separate tags with commas. The dropdown suggests tags you have used before, because the platforms don't offer a searchable tag list.
- **Platforms:** tick the platforms you want to update, then click **Apply to selected**.
- **Copy for TikTok:** TikTok has no API for LIVE titles, so this button copies your title and hashtags to the clipboard and opens TikTok so you can paste them.

## 8. Updating

**Manual:** replace `multitag.py` with the new file and run `bash install.sh` again.

**Automatic:** MultiTag checks its own GitHub repo for updates every time it starts, with nothing to set up. The built-in link is:

```
https://raw.githubusercontent.com/7JEO/MultiTag/refs/heads/main/multitag.py
```

On each launch, MultiTag checks that file. If its `VERSION` line is higher than the running version, it asks whether to install and restart. Bump `VERSION` in the file each time you publish a change. To use a different source, put its raw link in Settings → Update Url, which overrides the built-in link. Only use a repo you control, because the file it downloads runs as code on your machine. The previous version is kept as `multitag.py.bak`.

The window title shows the running version, for example *MultiTag 1.4.2*.

## 9. Uninstall

```
rm -rf ~/.local/share/multitag
rm -f ~/.local/share/applications/multitag.desktop
rm -f ~/.local/share/icons/hicolor/scalable/apps/multitag.svg
```

To also delete your saved credentials and logins:

```
rm -rf ~/.config/multitag
```

## 10. Troubleshooting

| Problem | What to try |
| --- | --- |
| No launcher entry or icon | Log out and back in, or restart Plasma (see section 3). Check that `grep Icon ~/.local/share/applications/multitag.desktop` shows a full path. |
| Login page never finishes | MultiTag listens on port 8976 during Kick and YouTube logins. Make sure nothing else is using it, and that the redirect URI is exactly `http://localhost:8976/callback`. |
| Twitch login fails right away | The Twitch app must have the **Public** client type. |
| "no active or upcoming broadcast found" (YouTube) | Create or start a live broadcast in YouTube Studio first. MultiTag edits the active one, or the first upcoming one. |
| YouTube asks for login every week | The Google consent screen is in Testing mode (see section 4). |
| Kick tags are empty when loading current info | Kick may not return tags in the place MultiTag reads them. Applying tags still works. |
| Category not applied | Twitch and Kick use the exact name if there is one, otherwise the top search result. Pick one from the dropdown for certainty. |
| "Update check failed" | Check your internet connection and that the GitHub repo is public. If you set a custom Update Url, make sure it is a raw link starting with `https://`. |

## 11. Known limitations

- YouTube: title and tags only. No category.
- Twitch tags can't contain spaces and are cut to 25 characters. Twitch and Kick take at most 10 tags.
- TikTok is clipboard-assisted only.
- The Twitch, Kick and YouTube calls were written from their public API documentation and have not been exhaustively tested, so report any `ERR` message you can't explain.
