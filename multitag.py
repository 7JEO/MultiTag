#!/usr/bin/env python3
"""MultiTag: update stream title / category / tags on Twitch, Kick and YouTube at once
(plus a copy-to-clipboard helper for TikTok, which has no API for this).
Deps (Arch): sudo pacman -S python-pyqt6 python-requests
"""
import base64, hashlib, json, os, re, secrets, shutil, sys, threading, time, urllib.parse, webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
import requests
from PyQt6.QtCore import QStringListModel, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QIcon, QPalette
from PyQt6.QtWidgets import (QApplication, QCheckBox, QCompleter, QDialog, QDialogButtonBox, QFormLayout, QFrame,
                             QHBoxLayout, QLineEdit, QListView, QMessageBox, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget)

VERSION = "1.4.2"  # bump this whenever you publish a new multitag.py
OLD_CFG = os.path.expanduser("~/.config/streamsync")  # pre-rename config, moved over once
CFG = os.path.expanduser("~/.config/multitag")
if os.path.isdir(OLD_CFG) and not os.path.exists(CFG):
    shutil.move(OLD_CFG, CFG)
os.makedirs(CFG, exist_ok=True)
CFG_F, TOK_F, HIST_F = CFG + "/config.json", CFG + "/tokens.json", CFG + "/history.json"
HLOCK = threading.Lock()
# Autocomplete dropdown: own background + accent border so it stands out from the log view (uses theme colours)
POPUP_CSS = """
QListView { background: palette(window); border: 2px solid palette(highlight); padding: 2px; outline: 0; }
QListView::item { padding: 4px 8px; }
QListView::item:selected { background: palette(highlight); color: palette(highlighted-text); }
"""
PORT = 8976
REDIRECT = f"http://localhost:{PORT}/callback"
LOCK = threading.Lock()
PROV = {
    "twitch": dict(tok="https://id.twitch.tv/oauth2/token", scope="channel:manage:broadcast"),
    "kick": dict(auth="https://id.kick.com/oauth/authorize", tok="https://id.kick.com/oauth/token",
                 scope="user:read channel:read channel:write"),
    "youtube": dict(auth="https://accounts.google.com/o/oauth2/v2/auth", tok="https://oauth2.googleapis.com/token",
                    scope="https://www.googleapis.com/auth/youtube.force-ssl"),
}


def load(p):
    try:
        return json.load(open(p))
    except Exception:
        return {}


def save(p, d):
    with open(os.open(p, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as f:
        json.dump(d, f, indent=1)


def chk(r):
    if not r.ok:
        raise RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")
    return r.json() if r.content else {}


def pick(items, q):
    if not items:
        raise RuntimeError(f"no category match for '{q}'")
    return next((i for i in items if i["name"].lower() == q.lower()), items[0])


# ---------- self-update ----------
def ver(src):
    m = re.search(r'^VERSION = "([\d.]+)"', src, re.M)
    return tuple(int(x) for x in m.group(1).split(".")) if m else (0,)


def fetch_update(url):
    """Return new source if the https URL hosts a newer, syntactically valid version, else None."""
    if not url.startswith("https://"):
        raise RuntimeError("update URL must be https")
    src = chk_text(requests.get(url, timeout=15))
    compile(src, "multitag.py", "exec")
    return src if ver(src) > ver(f'VERSION = "{VERSION}"') else None


def chk_text(r):
    if not r.ok:
        raise RuntimeError(f"HTTP {r.status_code}")
    return r.text


def install_update(src):
    me = os.path.abspath(__file__)
    open(me + ".new", "w").write(src)
    os.chmod(me + ".new", 0o755)
    shutil.copy2(me, me + ".bak")  # keep the previous version
    os.replace(me + ".new", me)


# ---------- auth ----------
def token_req(name, cfg, **d):
    d["client_id"] = cfg[name + "_id"]
    if cfg.get(name + "_secret"):
        d["client_secret"] = cfg[name + "_secret"]
    t = chk(requests.post(PROV[name]["tok"], data=d, timeout=20))
    t["expires_at"] = time.time() + t.get("expires_in", 3600) - 60
    return t


def catch_code():
    box = {}

    class H(BaseHTTPRequestHandler):
        def do_GET(s):
            box.update(urllib.parse.parse_qsl(urllib.parse.urlparse(s.path).query))
            s.send_response(200); s.send_header("Content-Type", "text/plain"); s.end_headers()
            s.wfile.write(b"Logged in. You can close this tab.")

        def log_message(s, *a): pass

    srv = HTTPServer(("localhost", PORT), H)
    srv.timeout = 180
    srv.handle_request()
    srv.server_close()
    return box


def login_pkce(name, cfg):
    p, ver, state = PROV[name], secrets.token_urlsafe(64), secrets.token_urlsafe(16)
    ch = base64.urlsafe_b64encode(hashlib.sha256(ver.encode()).digest()).rstrip(b"=").decode()
    q = dict(client_id=cfg[name + "_id"], response_type="code", redirect_uri=REDIRECT, scope=p["scope"],
             state=state, code_challenge=ch, code_challenge_method="S256")
    if name == "youtube":
        q.update(access_type="offline", prompt="consent")
    webbrowser.open(p["auth"] + "?" + urllib.parse.urlencode(q))
    got = catch_code()
    if got.get("state") != state or "code" not in got:
        raise RuntimeError("login failed or timed out")
    return token_req(name, cfg, grant_type="authorization_code", code=got["code"],
                     redirect_uri=REDIRECT, code_verifier=ver)


def login_twitch(cfg, log):  # device-code flow: no client secret needed (app must be "Public")
    sc = PROV["twitch"]["scope"]
    d = chk(requests.post("https://id.twitch.tv/oauth2/device",
                          data=dict(client_id=cfg["twitch_id"], scopes=sc), timeout=20))
    log(f"Twitch: authorize in browser (code {d['user_code']})")
    webbrowser.open(d["verification_uri"])
    end = time.time() + d.get("expires_in", 300)
    while time.time() < end:
        time.sleep(d.get("interval", 5))
        try:
            return token_req("twitch", cfg, scopes=sc, device_code=d["device_code"],
                             grant_type="urn:ietf:params:oauth:grant-type:device_code")
        except RuntimeError as e:
            if "pending" not in str(e).lower():
                raise
    raise RuntimeError("login timed out")


def get_token(name, cfg, log, login=True):  # login=False: return None instead of opening a browser
    with LOCK:
        T = load(TOK_F)
        t = T.get(name)
        if t and t["expires_at"] < time.time():
            try:
                t2 = token_req(name, cfg, grant_type="refresh_token", refresh_token=t["refresh_token"])
                t2.setdefault("refresh_token", t["refresh_token"])
                t = t2
            except Exception:
                t = None
        if not t and not login:
            return None
        if not t:
            t = login_twitch(cfg, log) if name == "twitch" else login_pkce(name, cfg)
        T[name] = t
        save(TOK_F, T)
        return t["access_token"]


# ---------- platforms ----------
def twitch(cfg, tok, title, cat, tags):
    H = {"Authorization": "Bearer " + tok, "Client-Id": cfg["twitch_id"]}
    B = "https://api.twitch.tv/helix"
    me = chk(requests.get(B + "/users", headers=H, timeout=20))["data"][0]["id"]
    body = {}
    if title: body["title"] = title
    if cat:
        r = chk(requests.get(B + "/search/categories", headers=H, params=dict(query=cat, first=10), timeout=20))
        body["game_id"] = pick(r["data"], cat)["id"]
    if tags: body["tags"] = [t.replace(" ", "")[:25] for t in tags[:10]]
    chk(requests.patch(B + "/channels", headers=H, params=dict(broadcaster_id=me), json=body, timeout=20))


def kick(cfg, tok, title, cat, tags):
    H = {"Authorization": "Bearer " + tok}
    B = "https://api.kick.com/public/v1"
    body = {}
    if title: body["stream_title"] = title
    if cat:
        r = chk(requests.get(B + "/categories", headers=H, params=dict(q=cat), timeout=20))
        body["category_id"] = int(pick(r["data"], cat)["id"])
    if tags: body["custom_tags"] = tags[:10]
    chk(requests.patch(B + "/channels", headers=H, json=body, timeout=20))


def youtube(cfg, tok, title, cat, tags):  # YouTube's API has no "game" category, so cat is ignored
    H = {"Authorization": "Bearer " + tok}
    B = "https://www.googleapis.com/youtube/v3"
    vid = None
    for st in ("active", "upcoming"):
        items = chk(requests.get(B + "/liveBroadcasts", headers=H, timeout=20,
                                 params=dict(part="id", mine="true", broadcastStatus=st))).get("items", [])
        if items:
            vid = items[0]["id"]
            break
    if not vid:
        raise RuntimeError("no active or upcoming broadcast found")
    sn = chk(requests.get(B + "/videos", headers=H, params=dict(part="snippet", id=vid), timeout=20))["items"][0]["snippet"]
    if title: sn["title"] = title
    if tags: sn["tags"] = tags
    keep = {k: sn[k] for k in ("title", "description", "categoryId", "tags") if k in sn}
    chk(requests.put(B + "/videos", headers=H, params=dict(part="snippet"), timeout=20,
                     json=dict(id=vid, snippet=keep)))


def twitch_info(cfg, tok):
    H = {"Authorization": "Bearer " + tok, "Client-Id": cfg["twitch_id"]}
    B = "https://api.twitch.tv/helix"
    me = chk(requests.get(B + "/users", headers=H, timeout=20))["data"][0]["id"]
    c = chk(requests.get(B + "/channels", headers=H, params=dict(broadcaster_id=me), timeout=20))["data"][0]
    return dict(title=c.get("title", ""), category=c.get("game_name", ""), tags=c.get("tags", []))


def kick_info(cfg, tok):
    r = chk(requests.get("https://api.kick.com/public/v1/channels", headers={"Authorization": "Bearer " + tok}, timeout=20))
    c = r["data"][0]
    return dict(title=c.get("stream_title", ""), category=(c.get("category") or {}).get("name", ""),
                tags=(c.get("stream") or {}).get("custom_tags", []))


def youtube_info(cfg, tok):
    H = {"Authorization": "Bearer " + tok}
    B = "https://www.googleapis.com/youtube/v3"
    for st in ("active", "upcoming"):
        items = chk(requests.get(B + "/liveBroadcasts", headers=H, timeout=20,
                                 params=dict(part="id", mine="true", broadcastStatus=st))).get("items", [])
        if items:
            sn = chk(requests.get(B + "/videos", headers=H, params=dict(part="snippet", id=items[0]["id"]), timeout=20))["items"][0]["snippet"]
            return dict(title=sn.get("title", ""), category="", tags=sn.get("tags", []))
    raise RuntimeError("no active or upcoming broadcast found")


INFOS = {"twitch": twitch_info, "kick": kick_info, "youtube": youtube_info}
def twitch_search(cfg, tok, q):
    H = {"Authorization": "Bearer " + tok, "Client-Id": cfg["twitch_id"]}
    r = chk(requests.get("https://api.twitch.tv/helix/search/categories", headers=H, params=dict(query=q, first=10), timeout=10))
    return [c["name"] for c in r.get("data", [])]


def kick_search(cfg, tok, q):
    r = chk(requests.get("https://api.kick.com/public/v1/categories", headers={"Authorization": "Bearer " + tok}, params=dict(q=q), timeout=10))
    return [c["name"] for c in r.get("data", [])]


def find_categories(cfg, q):
    """Category names matching q from every logged-in platform that has a category search (no login popups)."""
    out = []
    for n, fn in (("twitch", twitch_search), ("kick", kick_search)):
        try:
            tok = get_token(n, cfg, lambda m: None, login=False) if cfg.get(n + "_id") else None
            if tok: out += fn(cfg, tok, q)
        except Exception:
            pass
    seen = set()
    return [x for x in out if not (x.lower() in seen or seen.add(x.lower()))]


def remember(cat, tags):
    """Keep recently used categories/tags for autocomplete (no platform has a searchable tag list)."""
    with HLOCK:
        h = load(HIST_F)
        for k, vals in (("categories", [cat] if cat else []), ("tags", list(tags))):
            low = {v.lower() for v in vals}
            h[k] = (vals + [x for x in h.get(k, []) if x.lower() not in low])[:200]
        save(HIST_F, h)


FUNCS = {"twitch": twitch, "kick": kick, "youtube": youtube}


# ---------- GUI ----------
def style_popup(c):
    """Replace the completer's dropdown with one that has a visible frame, in two independent ways
    (a native QFrame border + the stylesheet), so at least one shows up whatever the desktop style does."""
    lv = QListView()
    lv.setEditTriggers(QListView.EditTrigger.NoEditTriggers)
    lv.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    lv.setSelectionBehavior(QListView.SelectionBehavior.SelectRows)
    lv.setSelectionMode(QListView.SelectionMode.SingleSelection)
    c.setPopup(lv)
    lv.setFrameStyle(QFrame.Shape.Box | QFrame.Shadow.Plain)
    lv.setLineWidth(2)
    pal = lv.palette()
    pal.setColor(QPalette.ColorRole.WindowText, pal.color(QPalette.ColorRole.Highlight))  # frame colour
    pal.setColor(QPalette.ColorRole.Base, pal.color(QPalette.ColorRole.Window))
    lv.setPalette(pal)
    lv.setStyleSheet(POPUP_CSS)


class TagCompleter(QCompleter):
    """Completes only the comma-separated item being typed."""
    def splitPath(self, path):
        return [path.split(",")[-1].strip()]

    def pathFromIndex(self, index):
        head = self.widget().text().rsplit(",", 1)
        return (head[0].strip() + ", " if len(head) > 1 else "") + super().pathFromIndex(index)


class Settings(QDialog):
    KEYS = ["twitch_id", "kick_id", "kick_secret", "youtube_id", "youtube_secret", "update_url"]

    def __init__(s, parent):
        super().__init__(parent)
        s.setWindowTitle("API credentials")
        f, cfg = QFormLayout(s), load(CFG_F)
        s.e = {k: QLineEdit(cfg.get(k, "")) for k in s.KEYS}
        for k, e in s.e.items():
            f.addRow(k.replace("_", " ").title(), e)
        b = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        b.accepted.connect(s.ok); b.rejected.connect(s.reject)
        f.addRow(b)

    def ok(s):
        save(CFG_F, {k: e.text().strip() for k, e in s.e.items()})
        s.accept()


class Win(QWidget):
    sig = pyqtSignal(str)
    found = pyqtSignal(str)
    cur = pyqtSignal(str, object)
    cats = pyqtSignal(str, object)
    hist = pyqtSignal()

    def __init__(s):
        super().__init__()
        s.setWindowTitle(f"MultiTag {VERSION}")
        s.resize(520, 420)
        s.title, s.cat, s.tags = QLineEdit(), QLineEdit(), QLineEdit()
        s.tags.setPlaceholderText("comma, separated")
        s.cat.setPlaceholderText("e.g. Just Chatting (Twitch/Kick)")
        s.cat_api = []
        s.cat_model, s.tag_model = QStringListModel(), QStringListModel()
        s.cat_comp, s.tag_comp = QCompleter(s.cat_model, s), TagCompleter(s.tag_model, s)
        for c in (s.cat_comp, s.tag_comp):
            c.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
            c.setFilterMode(Qt.MatchFlag.MatchContains)
        s.cat.setCompleter(s.cat_comp)
        s.tags.setCompleter(s.tag_comp)
        for c in (s.cat_comp, s.tag_comp):
            style_popup(c)
        s.timer = QTimer(singleShot=True, interval=300)  # wait for a pause in typing before searching
        s.timer.timeout.connect(s.search_cats)
        s.cat.textEdited.connect(lambda _: s.timer.start())
        s.refresh_models()
        s.chk = {n: QCheckBox(n.title()) for n in FUNCS}
        s.log = QPlainTextEdit(readOnly=True)
        f = QFormLayout()
        f.addRow("Title", s.title); f.addRow("Category", s.cat); f.addRow("Tags", s.tags)
        row = QHBoxLayout()
        for c in s.chk.values():
            c.setChecked(True); row.addWidget(c)
        go, st = QPushButton("Apply to selected"), QPushButton("Settings")
        go.clicked.connect(s.apply); st.clicked.connect(lambda: Settings(s).exec())
        rf = QPushButton("Refresh")
        rf.clicked.connect(s.load_current)
        tt = QPushButton("Copy for TikTok")
        tt.clicked.connect(s.tiktok)
        row.addStretch(); row.addWidget(tt); row.addWidget(rf); row.addWidget(st); row.addWidget(go)
        lay = QVBoxLayout(s)
        lay.addLayout(f); lay.addLayout(row); lay.addWidget(s.log)
        s.sig.connect(s.log.appendPlainText)
        s.found.connect(s.offer)
        s.cur.connect(s.show_cur)
        s.cats.connect(s.got_cats)
        s.hist.connect(s.refresh_models)
        threading.Thread(target=s.check, daemon=True).start()
        s.load_current()

    def apply(s):
        cfg = load(CFG_F)
        a = (s.title.text().strip(), s.cat.text().strip(), [t.strip() for t in s.tags.text().split(",") if t.strip()])
        for n, c in s.chk.items():
            if c.isChecked():
                threading.Thread(target=s.run, args=(n, cfg) + a, daemon=True).start()

    def refresh_models(s):
        s.tag_model.setStringList(load(HIST_F).get("tags", []))
        s.update_cat_model()

    def update_cat_model(s):
        seen, out = set(), []
        for x in s.cat_api + load(HIST_F).get("categories", []):
            if x.lower() not in seen:
                seen.add(x.lower()); out.append(x)
        s.cat_model.setStringList(out)

    def search_cats(s):
        q = s.cat.text().strip()
        if len(q) >= 2:
            threading.Thread(target=lambda: s.cats.emit(q, find_categories(load(CFG_F), q)), daemon=True).start()

    def got_cats(s, q, names):
        if q == s.cat.text().strip():  # ignore answers for text that has since changed
            s.cat_api = names
            s.update_cat_model()
            s.cat_comp.complete()

    def load_current(s):  # fills the fields from the first platform that answers
        s.filled = False
        threading.Thread(target=s.fetch_current, daemon=True).start()

    def fetch_current(s):
        cfg = load(CFG_F)
        for n, fn in INFOS.items():
            if not cfg.get(n + "_id"):
                continue
            try:
                tok = get_token(n, cfg, s.sig.emit, login=False)
                if not tok:
                    s.sig.emit(f"{n}: not logged in yet. Press Apply once to log in.")
                    continue
                s.cur.emit(n, fn(cfg, tok))
            except Exception as e:
                s.sig.emit(f"ERR {n} (reading current info): {e}")

    def show_cur(s, n, d):
        tags = ", ".join(d["tags"])
        remember(d["category"], d["tags"])
        s.refresh_models()
        s.log.appendPlainText(f"Current on {n}: {d['title']} | {d['category'] or '-'} | {tags or '-'}")
        if not s.filled:
            s.filled = True
            s.title.setText(d["title"]); s.cat.setText(d["category"]); s.tags.setText(tags)

    def check(s):
        url = load(CFG_F).get("update_url", "")
        if url:
            try:
                src = fetch_update(url)
                if src: s.found.emit(src)
            except Exception as e:
                s.sig.emit(f"Update check failed: {e}")

    def offer(s, src):
        v = ".".join(map(str, ver(src)))
        yes = QMessageBox.StandardButton.Yes
        if QMessageBox.question(s, "Update available", f"MultiTag {v} is available (you have {VERSION}). Install and restart?") == yes:
            try:
                install_update(src)
                os.execv(sys.executable, [sys.executable] + sys.argv)
            except Exception as e:
                s.sig.emit(f"Update failed: {e}")

    def tiktok(s):  # TikTok has no LIVE metadata API: copy text, open TikTok, paste it yourself
        tags = " ".join("#" + t.strip().lstrip("#").replace(" ", "") for t in s.tags.text().split(",") if t.strip())
        QApplication.clipboard().setText((s.title.text().strip() + " " + tags).strip())
        webbrowser.open("https://www.tiktok.com/live")
        s.sig.emit("Copied title + hashtags for TikTok. Paste them into TikTok's LIVE setup.")

    def run(s, n, cfg, title, cat, tags):
        try:
            if not cfg.get(n + "_id"):
                raise RuntimeError("set credentials in Settings first")
            FUNCS[n](cfg, get_token(n, cfg, s.sig.emit), title, cat, tags)
            s.sig.emit(f"OK  {n} updated")
            remember(cat if n != "youtube" else "", tags)
            s.hist.emit()
        except Exception as e:
            s.sig.emit(f"ERR {n}: {e}")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setApplicationName("multitag")  # X11 window class, matches StartupWMClass
    app.setDesktopFileName("multitag")  # lets KDE/Wayland match the window to the launcher entry
    svg = os.path.join(os.path.dirname(os.path.abspath(__file__)), "multitag.svg")
    app.setWindowIcon(QIcon(svg) if os.path.exists(svg) else QIcon.fromTheme("multitag"))
    w = Win(); w.show()
    sys.exit(app.exec())
