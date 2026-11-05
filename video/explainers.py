"""Illustrated scenes for the demo video (used by build_video_v3.py
--narration video/narration-illustrated.json).

Flat line drawings in the app's warm palette, animated with GSAP inside
the Hyperframes composition: people asking each other, knowledge stuck in
heads and laptops, a paid report nobody opened, four roles with locks,
two sources that disagree, a recording that becomes steps. Every scene
starts on the narration sentence it illustrates, so picture and voice
move together. Nothing here is a product screenshot; the real footage
stays in its own segments.
"""

import html
import json

INK = "#e4e4e7"
WARM = "#ffb37a"
DIM = "#52525b"

ICONS = {
    # 64x64 line icons; the person's head is a separate circle so it can glow.
    "person": '<circle cx="32" cy="20" r="11" fill="none" stroke="{c}" stroke-width="3"/>'
              '<path d="M12 58c0-12 9-20 20-20s20 8 20 20" fill="none" stroke="{c}" stroke-width="3" stroke-linecap="round"/>',
    "doc": '<path d="M16 6h22l12 12v40H16z" fill="none" stroke="{c}" stroke-width="3" stroke-linejoin="round"/>'
           '<path d="M38 6v12h12M23 30h20M23 39h20M23 48h13" fill="none" stroke="{c}" stroke-width="3" stroke-linecap="round"/>',
    "sheet": '<rect x="8" y="10" width="48" height="44" rx="4" fill="none" stroke="{c}" stroke-width="3"/>'
             '<path d="M8 24h48M8 38h48M24 10v44M40 10v44" stroke="{c}" stroke-width="2.5"/>',
    "slide": '<rect x="6" y="12" width="52" height="36" rx="4" fill="none" stroke="{c}" stroke-width="3"/>'
             '<path d="M20 40V30M30 40V22M40 40V27M32 48v8M22 58h20" stroke="{c}" stroke-width="3" stroke-linecap="round"/>',
    "video": '<rect x="6" y="12" width="52" height="40" rx="5" fill="none" stroke="{c}" stroke-width="3"/>'
             '<path d="M27 23v18l15-9z" fill="{c}"/>',
    "laptop": '<rect x="12" y="12" width="40" height="28" rx="3" fill="none" stroke="{c}" stroke-width="3"/>'
              '<path d="M4 50h56l-5-8H9z" fill="none" stroke="{c}" stroke-width="3" stroke-linejoin="round"/>',
    "lock": '<rect x="14" y="28" width="36" height="28" rx="5" fill="none" stroke="{c}" stroke-width="3"/>'
            '<path d="M22 28v-8a10 10 0 0 1 20 0v8" fill="none" stroke="{c}" stroke-width="3"/>'
            '<circle cx="32" cy="42" r="3.5" fill="{c}"/>',
    "check": '<circle cx="32" cy="32" r="24" fill="none" stroke="{c}" stroke-width="3"/>'
             '<path d="M21 33l8 8 15-17" fill="none" stroke="{c}" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>',
    "box": '<path d="M8 22l24-12 24 12v26L32 60 8 48z" fill="none" stroke="{c}" stroke-width="3" stroke-linejoin="round"/>'
           '<path d="M8 22l24 12 24-12M32 34v26" fill="none" stroke="{c}" stroke-width="3" stroke-linejoin="round"/>',
    "tag": '<path d="M6 30V8h22l30 30-22 22z" fill="none" stroke="{c}" stroke-width="3" stroke-linejoin="round"/>'
           '<circle cx="18" cy="20" r="4" fill="{c}"/>',
    "search": '<circle cx="27" cy="27" r="16" fill="none" stroke="{c}" stroke-width="4"/>'
              '<path d="M39 39l15 15" stroke="{c}" stroke-width="5" stroke-linecap="round"/>',
}


def icon(name, size=64, color=INK, cls="", id_=None, style=""):
    return ('<svg %sclass="ic %s" viewBox="0 0 64 64" width="%d" height="%d" style="%s">%s</svg>'
            % ('id="%s" ' % id_ if id_ else "", cls, size, size, style,
               ICONS[name].format(c=color)))


CSS = """
.ill { position: absolute; inset: 0; }
.ill .at { position: absolute; transform: translate(-50%, -50%); }
.tagpill { position: absolute; left: 50%; top: 46px; transform: translateX(-50%); font: 700 13px/1 Inter, sans-serif;
  letter-spacing: .16em; color: #ffcf8a; border: 1px solid rgba(255,207,138,.35); background: rgba(240,96,60,.10);
  border-radius: 999px; padding: 8px 16px; white-space: nowrap; }
.bubble { position: absolute; transform: translate(-50%, -100%); min-width: 46px; height: 40px; padding: 0 12px; border-radius: 14px;
  background: #18181b; border: 2px solid #ffb37a; color: #ffcf8a; font: 800 24px/36px Inter, sans-serif; text-align: center; }
.bubble.grey { border-color: #52525b; color: #a1a1aa; }
.lbl { position: absolute; transform: translateX(-50%); font: 600 16px/1.2 Inter, sans-serif; color: #d4d4d8; white-space: nowrap; text-align: center; }
.lbl small { display: block; font-weight: 500; font-size: 13px; color: #a1a1aa; margin-top: 3px; }
.dash { position: absolute; height: 0; border-top: 3px dashed rgba(255,179,122,.7); transform-origin: 0 50%; }
.glowdot { position: absolute; width: 150px; height: 150px; border-radius: 50%; transform: translate(-50%,-50%);
  background: radial-gradient(circle, rgba(255,179,122,.30), transparent 65%); }
.card2 { position: absolute; transform: translate(-50%, -50%); background: rgba(24,24,27,.92); border: 1px solid rgba(255,255,255,.14);
  border-radius: 14px; box-shadow: 0 20px 50px rgba(0,0,0,.45); padding: 18px 20px; font-family: Inter, sans-serif; color: #f4f4f5; }
.card2 .k { font-size: 13px; color: #a1a1aa; }
.card2 .v { font-size: 54px; font-weight: 800; letter-spacing: -0.03em; line-height: 1.05; margin-top: 6px; }
.stamp { position: absolute; transform: translate(-50%,-50%) rotate(-8deg); font: 800 18px/1 Inter, sans-serif; letter-spacing: .1em;
  color: #86efac; border: 3px solid #86efac; border-radius: 8px; padding: 8px 12px; background: rgba(10,10,11,.6); }
.strike { position: absolute; height: 4px; background: #f87171; transform-origin: 0 50%; }
.av { position: absolute; transform: translate(-50%,-50%); width: 58px; height: 58px; border-radius: 50%; display: flex; align-items: center;
  justify-content: center; font: 700 18px/1 Inter, sans-serif; color: #0a0a0b; }
.cell { position: absolute; transform: translate(-50%,-50%); }
.rowlbl { position: absolute; transform: translateY(-50%); font: 600 17px/1.2 Inter, sans-serif; color: #e4e4e7; }
.rowlbl small { display: block; font-size: 13px; color: #a1a1aa; font-weight: 500; }
.tline { position: absolute; height: 10px; border-radius: 5px; background: rgba(228,228,231,.55); }
.step { position: absolute; transform: translate(-50%,-50%); width: 300px; background: rgba(24,24,27,.92); border: 1px solid rgba(255,255,255,.14);
  border-radius: 12px; padding: 12px 14px; font: 600 16px/1.3 Inter, sans-serif; color: #f4f4f5; display: flex; gap: 12px; align-items: center; }
.step .n { flex: none; width: 30px; height: 30px; border-radius: 50%; background: #ffb37a; color: #0a0a0b; font-weight: 800; display: flex;
  align-items: center; justify-content: center; }
.step .t { font: 500 13px 'DejaVu Sans Mono', monospace; color: #ffb37a; margin-left: auto; }
.searchbar { position: absolute; left: 50%; top: 52%; transform: translate(-50%,-50%); width: 560px; height: 76px; border-radius: 16px;
  background: rgba(24,24,27,.92); border: 1px solid rgba(255,255,255,.18); box-shadow: 0 24px 60px rgba(0,0,0,.5);
  display: flex; align-items: center; gap: 16px; padding: 0 22px; font: 500 22px Inter, sans-serif; color: #f4f4f5; }
.bigpct { position: absolute; transform: translate(-50%,-50%); font: 800 120px/1 Inter, sans-serif; letter-spacing: -0.05em;
  background: linear-gradient(90deg, #ffcf8a, #f0603c); -webkit-background-clip: text; background-clip: text; color: transparent; }
.small2 { position: absolute; transform: translateX(-50%); font: 500 17px/1.35 Inter, sans-serif; color: #a1a1aa; text-align: center; white-space: nowrap; }
"""


def _at(x, y, inner, id_, extra=""):
    return '<div class="at" id="%s" style="left:%dpx;top:%dpx;%s">%s</div>' % (id_, x, y, extra, inner)


def _cue_start(seg, prefix):
    for c0, _, txt in seg["cues"]:
        if txt.startswith(prefix):
            return seg["start"] + seg["lead"] + c0
    raise KeyError(prefix)


# ------------------------------------------------------------------ opening

def opening(seg):
    """Five illustrated beats, each starting on its narration sentence."""
    a, d = seg["start"], seg["len"]
    t1 = a + 0.2
    t2 = _cue_start(seg, "Know-how")
    t3 = _cue_start(seg, "Data the company")
    t5 = _cue_start(seg, "Atlassian")
    t6 = _cue_start(seg, "Kohu is one")
    end = a + d
    H, J = [], []

    # Beat 1: a new hire asks, gets passed from person to person.
    xs = [300, 560, 820, 1060]
    b1 = ['<div class="tagpill">THE PROBLEM</div>']
    for i, x in enumerate(xs):
        col = WARM if i == 0 else INK
        b1.append(_at(x, 400, icon("person", 110, col), "p%d" % i))
        b1.append('<div class="bubble%s" id="q%d" style="left:%dpx;top:328px">?</div>' % ("" if i == 0 else " grey", i, x))
    b1.append('<div class="lbl" id="nh" style="left:300px;top:470px">New hire</div>')
    for i in range(3):
        x0, x1 = xs[i] + 62, xs[i + 1] - 62
        b1.append('<div class="dash" id="d%d" style="left:%dpx;top:400px;width:%dpx"></div>' % (i, x0, x1 - x0))
    H.append('<div class="clip ill" id="sc1" data-start="%.3f" data-duration="%.3f">%s</div>' % (t1, t3 - t1, "".join(b1)))
    J.append('tl.fromTo("#sc1 .tagpill", {opacity: 0, y: -10}, {opacity: 1, y: 0, duration: .4}, %.3f);' % t1)
    J.append('tl.fromTo("#p0", {opacity: 0, scale: .6}, {opacity: 1, scale: 1, duration: .45, ease: "back.out(1.8)"}, %.3f);' % (t1 + .1))
    J.append('tl.fromTo("#nh", {opacity: 0}, {opacity: 1, duration: .3}, %.3f);' % (t1 + .3))
    J.append('tl.fromTo("#q0", {opacity: 0, scale: .4}, {opacity: 1, scale: 1, duration: .35, ease: "back.out(2)"}, %.3f);' % (t1 + .45))
    step = max(0.55, (t2 - t1 - 1.0) / 3)
    for i in range(3):
        s = t1 + 0.75 + i * step
        J.append('tl.fromTo("#d%d", {scaleX: 0}, {scaleX: 1, duration: .35, ease: "power2.out"}, %.3f);' % (i, s))
        J.append('tl.fromTo("#p%d", {opacity: 0, scale: .6}, {opacity: 1, scale: 1, duration: .4, ease: "back.out(1.8)"}, %.3f);' % (i + 1, s + .2))
        J.append('tl.fromTo("#q%d", {opacity: 0, scale: .4}, {opacity: 1, scale: 1, duration: .3, ease: "back.out(2)"}, %.3f);' % (i + 1, s + .45))
    J.append('tl.to("#sc1 .dash, #sc1 .bubble, #nh", {opacity: 0, duration: .3}, %.3f);' % (t2 - .1))

    # Beat 2: knowledge sits in heads and on laptops (same people stay on screen).
    b2 = []
    for i, (x, kind) in enumerate([(560, "doc"), (820, "sheet"), (1060, "slide")]):
        b2.append('<div class="glowdot" id="g%d" style="left:%dpx;top:330px"></div>' % (i, x))
        b2.append(_at(x, 300, icon(kind, 46, WARM), "k%d" % i))
    for i, x in enumerate([600, 900]):
        b2.append(_at(x, 590, icon("laptop", 90, INK), "lt%d" % i))
        b2.append(_at(x, 584, icon("lock", 26, WARM), "lk%d" % i))
    b2.append('<div class="lbl" id="kl" style="left:300px;top:470px">still asking</div>')
    H.append('<div class="clip ill" id="sc2" data-start="%.3f" data-duration="%.3f">%s</div>' % (t2, t3 - t2, "".join(b2)))
    for i in range(3):
        J.append('tl.fromTo("#g%d", {opacity: 0, scale: .5}, {opacity: 1, scale: 1, duration: .5}, %.3f);' % (i, t2 + .15 * i))
        J.append('tl.fromTo("#k%d", {opacity: 0, y: 20}, {opacity: 1, y: 0, duration: .45, ease: "back.out(1.6)"}, %.3f);' % (i, t2 + .15 * i + .1))
    for i in range(2):
        J.append('tl.fromTo("#lt%d", {opacity: 0, y: 24}, {opacity: 1, y: 0, duration: .45}, %.3f);' % (i, t2 + .7 + .15 * i))
        J.append('tl.fromTo("#lk%d", {opacity: 0, scale: .4}, {opacity: 1, scale: 1, duration: .3, ease: "back.out(2)"}, %.3f);' % (i, t2 + 1.0 + .15 * i))
    J.append('tl.fromTo("#kl", {opacity: 0}, {opacity: 1, duration: .3}, %.3f);' % (t2 + .9))
    J.append('tl.to("#sc1, #sc2", {opacity: 0, duration: .35}, %.3f);' % (t3 - .35))

    # Beat 3 and 4: a report the company paid for, sealed and dusty.
    b3 = ['<div class="tagpill">PAID FOR, NEVER OPENED</div>',
          _at(640, 360, icon("box", 190, INK), "bx"),
          _at(790, 280, icon("tag", 80, WARM), "tg"),
          '<div class="lbl" id="tgl" style="left:640px;top:480px">Licensed report<small>the whole company may use it</small></div>']
    for i, (x, y) in enumerate([(560, 300), (700, 250), (610, 420), (720, 400), (530, 380)]):
        b3.append('<div class="at" id="dust%d" style="left:%dpx;top:%dpx;width:7px;height:7px;border-radius:50%%;background:#71717a"></div>' % (i, x, y))
    H.append('<div class="clip ill" id="sc3" data-start="%.3f" data-duration="%.3f">%s</div>' % (t3, t5 - t3, "".join(b3)))
    J.append('tl.fromTo("#sc3 .tagpill", {opacity: 0, y: -10}, {opacity: 1, y: 0, duration: .4}, %.3f);' % t3)
    J.append('tl.fromTo("#bx", {opacity: 0, y: 40}, {opacity: 1, y: 0, duration: .55, ease: "power3.out"}, %.3f);' % (t3 + .1))
    J.append('tl.fromTo("#tg", {opacity: 0, rotation: -30, scale: .5}, {opacity: 1, rotation: 0, scale: 1, duration: .5, ease: "back.out(1.8)"}, %.3f);' % (t3 + .45))
    J.append('tl.fromTo("#tgl", {opacity: 0}, {opacity: 1, duration: .4}, %.3f);' % (t3 + .7))
    for i in range(5):
        J.append('tl.fromTo("#dust%d", {opacity: 0, y: -14}, {opacity: .9, y: 0, duration: 1.1, ease: "sine.out"}, %.3f);' % (i, t3 + 1.0 + .25 * i))
    J.append('tl.to("#sc3", {opacity: 0, duration: .35}, %.3f);' % (t5 - .35))

    # Beat 5: a quarter of the time goes to searching.
    b5 = ['<svg class="at" id="pie" width="230" height="230" viewBox="0 0 230 230" style="left:420px;top:350px">'
          '<circle cx="115" cy="115" r="96" fill="none" stroke="#27272a" stroke-width="26"/>'
          '<circle id="arc" cx="115" cy="115" r="96" fill="none" stroke="url(#pg)" stroke-width="26" stroke-linecap="butt" '
          'stroke-dasharray="603.2" stroke-dashoffset="603.2" transform="rotate(-90 115 115)"/>'
          '<defs><linearGradient id="pg" x1="0" x2="1"><stop offset="0" stop-color="#ffcf8a"/><stop offset="1" stop-color="#f0603c"/></linearGradient></defs></svg>',
          _at(420, 350, icon("search", 70, INK), "srch"),
          '<div class="bigpct" id="pct2" style="left:790px;top:320px">0%</div>',
          '<div class="small2" id="pctl" style="left:790px;top:400px">of a team\'s time goes to<br>searching for answers</div>',
          '<div class="small2" id="pcts" style="left:640px;top:560px;font-size:14px">Atlassian, State of Teams 2025, about 12,000 knowledge workers</div>']
    H.append('<div class="clip ill" id="sc5" data-start="%.3f" data-duration="%.3f">%s</div>' % (t5, t6 - t5, "".join(b5)))
    J.append('tl.fromTo("#pie, #srch", {opacity: 0, scale: .8}, {opacity: 1, scale: 1, duration: .5, ease: "power3.out"}, %.3f);' % t5)
    J.append('tl.to("#arc", {attr: {"stroke-dashoffset": 452.4}, duration: 1.5, ease: "power2.out"}, %.3f);' % (t5 + .3))
    J.append('const pc2 = {v: 0}; tl.to(pc2, {v: 25, duration: 1.5, ease: "power2.out", onUpdate: () => { document.getElementById("pct2").textContent = Math.round(pc2.v) + "%%"; }}, %.3f);' % (t5 + .3))
    J.append('tl.fromTo("#pct2, #pctl", {opacity: 0, x: 20}, {opacity: 1, x: 0, duration: .5}, %.3f);' % (t5 + .2))
    J.append('tl.fromTo("#pcts", {opacity: 0}, {opacity: 1, duration: .5}, %.3f);' % (t5 + 1.2))
    J.append('tl.to("#sc5", {opacity: 0, duration: .35}, %.3f);' % (t6 - .35))

    # Beat 6: every kind of source flies into one search bar.
    b6 = ['<div class="searchbar" id="sbar">%s<span id="sbt">Ask Kohu</span></div>' % icon("search", 30, WARM)]
    spots = [("doc", 180, 160), ("sheet", 1100, 170), ("slide", 170, 560), ("video", 1110, 560), ("doc", 640, 120), ("laptop", 640, 620)]
    for i, (k, x, y) in enumerate(spots):
        b6.append(_at(x, y, icon(k, 70, INK if i % 2 else WARM), "fl%d" % i))
    H.append('<div class="clip ill" id="sc6" data-start="%.3f" data-duration="%.3f">%s</div>' % (t6, end - t6, "".join(b6)))
    J.append('tl.fromTo("#sc6 .at", {opacity: 0, scale: .6}, {opacity: 1, scale: 1, duration: .35, stagger: .06}, %.3f);' % t6)
    J.append('tl.fromTo("#sbar", {opacity: 0, scale: .9}, {opacity: 1, scale: 1, duration: .45, ease: "power3.out"}, %.3f);' % (t6 + .2))
    for i, (k, x, y) in enumerate(spots):
        J.append('tl.to("#fl%d", {left: 640, top: 374, scale: .2, opacity: 0, duration: .6, ease: "power2.in"}, %.3f);' % (i, t6 + .7 + .08 * i))
    J.append('tl.fromTo("#sbar", {boxShadow: "0 24px 60px rgba(0,0,0,.5)"}, {boxShadow: "0 0 0 3px rgba(255,179,122,.6), 0 24px 60px rgba(0,0,0,.5)", duration: .3, yoyo: true, repeat: 1}, %.3f);' % (t6 + 1.3))
    J.append('tl.to("#sc6", {opacity: 0, duration: .3}, %.3f);' % (end - .3))
    return "\n".join(H), "\n".join(J)


# --------------------------------------------------------------- explainers

ROLES = [("NH", "#ffcf8a", "New hire"), ("AN", "#93c5fd", "Analyst"), ("MG", "#86efac", "Manager"), ("DA", "#f9a8d4", "Data admin")]
ACCESS = [("Refund process", "every role", [1, 1, 1, 1]),
          ("ASEAN dataset", "few licensed seats", [0, 1, 0, 1]),
          ("Team performance", "managers only", [0, 0, 1, 1])]


def roles(seg):
    a, d = seg["start"], seg["len"]
    H = ['<div class="tagpill">WHO SEES WHAT</div>']
    J = ['tl.fromTo("#xr .tagpill", {opacity: 0, y: -10}, {opacity: 1, y: 0, duration: .4}, %.3f);' % a]
    cols = [560, 720, 880, 1040]
    for j, (ini, col, name) in enumerate(ROLES):
        H.append('<div class="av" id="ra%d" style="left:%dpx;top:190px;background:%s">%s</div>' % (j, cols[j], col, ini))
        H.append('<div class="lbl" id="rn%d" style="left:%dpx;top:232px;font-size:14px">%s</div>' % (j, cols[j], name))
        J.append('tl.fromTo("#ra%d, #rn%d", {opacity: 0, y: -16}, {opacity: 1, y: 0, duration: .4, ease: "back.out(1.6)"}, %.3f);' % (j, j, a + .2 + .12 * j))
    rows = [340, 450, 560]
    for i, (title, note, ok) in enumerate(ACCESS):
        H.append(_at(200, rows[i], icon("doc" if i == 0 else "sheet", 52, INK), "rd%d" % i))
        H.append('<div class="rowlbl" id="rl%d" style="left:244px;top:%dpx">%s<small>%s</small></div>' % (i, rows[i], title, note))
        t = a + 1.0 + i * max(0.5, (d - 2.0) / 3)
        J.append('tl.fromTo("#rd%d, #rl%d", {opacity: 0, x: -20}, {opacity: 1, x: 0, duration: .4}, %.3f);' % (i, i, t))
        for j in range(4):
            H.append('<div class="cell" id="c%d_%d" style="left:%dpx;top:%dpx">%s</div>'
                     % (i, j, cols[j], rows[i], icon("check" if ok[j] else "lock", 44, "#86efac" if ok[j] else DIM)))
            J.append('tl.fromTo("#c%d_%d", {opacity: 0, scale: .3}, {opacity: 1, scale: 1, duration: .3, ease: "back.out(2)"}, %.3f);' % (i, j, t + .25 + .1 * j))
    J.append('tl.to("#xr", {opacity: 0, duration: .3}, %.3f);' % (a + d - .3))
    return ('<div class="clip ill" id="xr" data-start="%.3f" data-duration="%.3f">%s</div>' % (a, d, "".join(H)), "\n".join(J))


def conflict(seg):
    a, d = seg["start"], seg["len"]
    H = ['<div class="tagpill">TWO SOURCES DISAGREE</div>',
         '<div class="card2" id="cA" style="left:400px;top:330px;width:330px"><div class="k">ASEAN report, licensed, page 3</div>'
         '<div class="v">5.0%</div><div class="k">Viet Nam growth, 2023</div></div>',
         '<div class="card2" id="cB" style="left:880px;top:330px;width:330px"><div class="k">Expansion deck, internal, slide 4</div>'
         '<div class="v">6.5%</div><div class="k">Viet Nam growth, 2023</div></div>',
         '<div class="at" id="neq" style="left:640px;top:330px;font:800 64px/1 Inter,sans-serif;color:#ffb37a">&#8800;</div>',
         '<div class="av" id="cda" style="left:640px;top:540px;background:#f9a8d4">DA</div>',
         '<div class="lbl" id="cdl" style="left:640px;top:582px;font-size:14px">Data admin decides</div>',
         '<div class="stamp" id="cst" style="left:400px;top:440px">SOURCE OF RECORD</div>',
         '<div class="strike" id="cx" style="left:800px;top:330px;width:170px"></div>']
    J = ['tl.fromTo("#xc .tagpill", {opacity: 0, y: -10}, {opacity: 1, y: 0, duration: .4}, %.3f);' % a,
         'tl.fromTo("#cA", {opacity: 0, x: -40}, {opacity: 1, x: 0, duration: .5, ease: "power3.out"}, %.3f);' % (a + .2),
         'tl.fromTo("#cB", {opacity: 0, x: 40}, {opacity: 1, x: 0, duration: .5, ease: "power3.out"}, %.3f);' % (a + .45),
         'tl.fromTo("#neq", {opacity: 0, scale: .4}, {opacity: 1, scale: 1, duration: .4, ease: "back.out(2)"}, %.3f);' % (a + .9),
         'tl.to("#neq", {scale: 1.15, duration: .3, yoyo: true, repeat: 3}, %.3f);' % (a + 1.3),
         'tl.fromTo("#cda, #cdl", {opacity: 0, y: 30}, {opacity: 1, y: 0, duration: .45, ease: "back.out(1.6)"}, %.3f);' % (a + d * .45),
         'tl.fromTo("#cst", {opacity: 0, scale: 2.2}, {opacity: 1, scale: 1, duration: .35, ease: "power4.in"}, %.3f);' % (a + d * .6),
         'tl.fromTo("#cx", {scaleX: 0}, {scaleX: 1, duration: .35}, %.3f);' % (a + d * .6 + .3),
         'tl.to("#cB", {opacity: .45, duration: .4}, %.3f);' % (a + d * .6 + .3),
         'tl.to("#xc", {opacity: 0, duration: .3}, %.3f);' % (a + d - .3)]
    return ('<div class="clip ill" id="xc" data-start="%.3f" data-duration="%.3f">%s</div>' % (a, d, "".join(H)), "\n".join(J))


STEPS = [("1", "Open Orders", "0:05"), ("2", "Search the order", "0:08"), ("3", "Check it was delivered", "0:14")]


def recording(seg):
    a, d = seg["start"], seg["len"]
    H = ['<div class="tagpill">SCREEN RECORDINGS</div>',
         _at(250, 360, icon("video", 170, INK), "rv"),
         '<div class="at" id="rbar" style="left:250px;top:470px;width:150px;height:6px;border-radius:3px;background:#3f3f46">'
         '<div id="rbarf" style="height:100%;width:100%;background:#ffb37a;border-radius:3px;transform-origin:0 50%"></div></div>']
    for i, w in enumerate([150, 120, 140, 90]):
        H.append('<div class="tline" id="tl%d" style="left:460px;top:%dpx;width:%dpx"></div>' % (i, 300 + 32 * i, w))
    for i, (n, txt, ts) in enumerate(STEPS):
        H.append('<div class="step" id="st%d" style="left:960px;top:%dpx"><span class="n">%s</span>%s<span class="t">%s</span></div>'
                 % (i, 270 + 90 * i, n, html.escape(txt), ts))
    J = ['tl.fromTo("#xv .tagpill", {opacity: 0, y: -10}, {opacity: 1, y: 0, duration: .4}, %.3f);' % a,
         'tl.fromTo("#rv, #rbar", {opacity: 0, scale: .8}, {opacity: 1, scale: 1, duration: .45, ease: "back.out(1.6)"}, %.3f);' % (a + .2),
         'tl.fromTo("#rbarf", {scaleX: 0}, {scaleX: 1, duration: %.2f, ease: "none"}, %.3f);' % (max(1.0, d - 1.2), a + .5)]
    for i in range(4):
        J.append('tl.fromTo("#tl%d", {opacity: 0, scaleX: 0, transformOrigin: "0 50%%"}, {opacity: 1, scaleX: 1, duration: .35}, %.3f);' % (i, a + .8 + .18 * i))
    for i in range(3):
        J.append('tl.fromTo("#st%d", {opacity: 0, x: 40}, {opacity: 1, x: 0, duration: .4, ease: "power3.out"}, %.3f);' % (i, a + 1.6 + .3 * i))
    J.append('tl.to("#xv", {opacity: 0, duration: .3}, %.3f);' % (a + d - .3))
    return ('<div class="clip ill" id="xv" data-start="%.3f" data-duration="%.3f">%s</div>' % (a, d, "".join(H)), "\n".join(J))


SCENES = {"x-roles": roles, "x-conflict": conflict, "x-video": recording}
MIN_LEN = {"x-roles": 6.5, "x-conflict": 6.5, "x-video": 5.5}
