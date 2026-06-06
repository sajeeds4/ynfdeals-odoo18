# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request


UNDER_CONSTRUCTION_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<meta name="robots" content="noindex, nofollow"/>
<title>YNF Deals — Coming soon</title>
<link rel="preconnect" href="https://fonts.googleapis.com"/>
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin="crossorigin"/>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,500;0,600;0,700;1,500;1,600&amp;family=Inter:wght@400;500;600;700&amp;display=swap"/>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
html, body { height: 100%; }
body {
  font-family: 'Inter', system-ui, -apple-system, sans-serif;
  background: radial-gradient(ellipse at top right, #3d2d1c 0%, #1c1209 70%);
  color: #f3e9d6;
  min-height: 100vh;
  display: flex; align-items: center; justify-content: center;
  padding: 24px;
}
.uc-wrap { max-width: 560px; width: 100%; text-align: center; }
.uc-logo {
  width: 56px; height: 56px;
  margin: 0 auto 28px;
  border: 2px solid #c9a961; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
}
.uc-logo span {
  font-family: 'Cormorant Garamond', serif; font-style: italic;
  color: #c9a961; font-size: 30px; line-height: 1;
}
.uc-brand {
  letter-spacing: 0.22em; font-size: 12px; font-weight: 600;
  color: #c9bca0; margin-bottom: 24px;
}
.uc-title {
  font-family: 'Cormorant Garamond', serif; font-weight: 500;
  font-size: 64px; line-height: 1.05; color: #f8efdd; margin-bottom: 18px;
}
.uc-title em { font-style: italic; color: #c9a961; font-weight: 500; }
.uc-sub {
  font-size: 15.5px; line-height: 1.6; color: #c9bca0;
  margin: 0 auto 36px; max-width: 440px;
}
.uc-divider { width: 60px; height: 1px; background: #6b5638; margin: 0 auto 32px; }
.uc-meta { font-size: 12.5px; color: #8a7a5c; letter-spacing: 0.05em; margin-bottom: 10px; }
.uc-meta a {
  color: #c9a961; text-decoration: none;
  border-bottom: 1px solid transparent; transition: border-color .15s ease;
}
.uc-meta a:hover { border-bottom-color: #c9a961; }
.uc-foot {
  margin-top: 48px; font-size: 11px; letter-spacing: 0.08em;
  color: #6b5638; text-transform: uppercase;
}
@media (max-width: 540px) {
  .uc-title { font-size: 44px; }
  .uc-sub { font-size: 14.5px; }
}
</style>
</head>
<body>
  <main class="uc-wrap">
    <div class="uc-logo"><span>Y</span></div>
    <div class="uc-brand">YNF DEALS</div>
    <h1 class="uc-title">Something <em>special</em><br/>is brewing.</h1>
    <p class="uc-sub">
      We're putting the final touches on our store.
      Authentic Arabian fragrances, live-auction prices,
      and a homepage worth the wait.
    </p>
    <div class="uc-divider"></div>
    <p class="uc-meta">Questions? <a href="mailto:hello@ynfdeals.com">hello@ynfdeals.com</a></p>
    <p class="uc-meta">Catch our live drops on TikTok @ynfdeals</p>
    <p class="uc-foot">© 2026 YNF Deals · launching soon</p>
  </main>
</body>
</html>
"""


class YNFDevGate(http.Controller):
    """Serves the public 'site under development' landing while ynf.dev_mode is on."""

    @http.route("/under-construction", type="http", auth="public", website=False, sitemap=False, csrf=False)
    def under_construction(self, **kw):
        return request.make_response(
            UNDER_CONSTRUCTION_HTML,
            headers=[
                ("Content-Type", "text/html; charset=utf-8"),
                ("Cache-Control", "no-store"),
                ("X-Robots-Tag", "noindex, nofollow"),
            ],
        )
