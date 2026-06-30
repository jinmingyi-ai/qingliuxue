from __future__ import annotations

import base64
import re
import sys
from pathlib import Path

import streamlit


APP_TITLE = "轻留学 | AI 留学助手"
ROOT = Path(__file__).resolve().parents[1]
LOGO = ROOT / "app" / "frontend" / "assets" / "qingliuxue-logo-mark.png"


def _streamlit_index() -> Path:
    package_dir = Path(streamlit.__file__).resolve().parent
    candidates = [
        package_dir / "static" / "index.html",
        package_dir / "web" / "server" / "static" / "index.html",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError("Could not locate Streamlit index.html")


def _favicon_link() -> str:
    if not LOGO.exists():
        return ""
    data = base64.b64encode(LOGO.read_bytes()).decode("ascii")
    return f'<link rel="icon" type="image/png" href="data:image/png;base64,{data}">'


def _logo_data_uri() -> str:
    if not LOGO.exists():
        return ""
    data = base64.b64encode(LOGO.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{data}"


def _patch_html(html: str) -> str:
    favicon = _favicon_link()
    logo_uri = _logo_data_uri()
    loader_logo = f'background-image: url("{logo_uri}");' if logo_uri else ""
    shell_css = """
<style id="qingliuxue-shell-patch">
html, body, #root {
  background: #fff8f5 !important;
}
body {
  margin: 0;
}
#qingliuxue-shell-loader {
  position: fixed;
  inset: 0;
  z-index: 2147483647;
  display: grid;
  place-items: center;
  background: #fff8f5;
  color: #9a3d2c;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}
#qingliuxue-shell-loader .ql-shell-inner {
  display: grid;
  justify-items: center;
  gap: 14px;
  transform: translateY(-8vh);
}
#qingliuxue-shell-loader .ql-shell-logo {
  width: 58px;
  height: 58px;
  background-size: contain;
  background-repeat: no-repeat;
  background-position: center;
  border-radius: 14px;
  animation: qlShellPulse 1.4s ease-in-out infinite;
}
#qingliuxue-shell-loader .ql-shell-title {
  font-size: 18px;
  font-weight: 900;
  letter-spacing: 0;
}
html.ql-app-ready #qingliuxue-shell-loader {
  display: none;
}
@keyframes qlShellPulse {
  0%, 100% { transform: scale(1); opacity: 0.72; }
  50% { transform: scale(1.04); opacity: 1; }
}
#MainMenu, header, footer,
[data-testid="stHeader"],
[data-testid="stToolbar"],
[data-testid="stDecoration"],
[data-testid="stStatusWidget"],
[data-testid="stDeployButton"] {
  display: none !important;
  visibility: hidden !important;
  height: 0 !important;
  opacity: 0 !important;
}
[data-testid="stSkeleton"],
.stSkeleton,
div[class*="skeleton"],
div[class*="Skeleton"],
div[data-testid*="Skeleton"] {
  display: none !important;
  visibility: hidden !important;
  opacity: 0 !important;
}
</style>
""".replace("background-size: contain;", f"{loader_logo}\n  background-size: contain;", 1).strip()

    shell_loader = """
<div id="qingliuxue-shell-loader" aria-label="轻留学正在加载">
  <div class="ql-shell-inner">
    <div class="ql-shell-logo"></div>
    <div class="ql-shell-title">轻留学</div>
  </div>
</div>
<script id="qingliuxue-shell-ready">
(function () {
  function markReady() {
    if (document.querySelector(".stApp")) {
      document.documentElement.classList.add("ql-app-ready");
      return;
    }
    window.requestAnimationFrame(markReady);
  }
  window.requestAnimationFrame(markReady);
})();
</script>
""".strip()

    html = re.sub(r"<title>.*?</title>", f"<title>{APP_TITLE}</title>", html, count=1, flags=re.IGNORECASE | re.DOTALL)
    html = re.sub(
        r"\s*<link[^>]+rel=[\"'][^\"']*(?:icon|mask-icon|apple-touch-icon)[^\"']*[\"'][^>]*>",
        "",
        html,
        flags=re.IGNORECASE,
    )
    if favicon and "</head>" in html:
        html = html.replace("</head>", f"{favicon}\n{shell_css}\n</head>", 1)
    elif "</head>" in html:
        html = html.replace("</head>", f"{shell_css}\n</head>", 1)
    html = re.sub(
        r"(<body[^>]*>)",
        lambda match: f"{match.group(1)}\n{shell_loader}",
        html,
        count=1,
        flags=re.IGNORECASE,
    )
    return html


def main() -> None:
    strict = "--strict" in sys.argv
    try:
        index_path = _streamlit_index()
    except FileNotFoundError as exc:
        message = "Could not locate Streamlit index.html"
        if strict:
            raise FileNotFoundError(message) from exc
        print(message)
        return

    html = index_path.read_text(encoding="utf-8")
    if "qingliuxue-shell-patch" in html:
        print(f"Streamlit shell already patched: {index_path}")
        return

    html = _patch_html(html)

    try:
        index_path.write_text(html, encoding="utf-8")
    except PermissionError as exc:
        message = f"Could not patch Streamlit shell due to permissions: {index_path}"
        if strict:
            raise PermissionError(message) from exc
        print(message)
        return
    print(f"Patched Streamlit shell: {index_path}")


if __name__ == "__main__":
    main()
