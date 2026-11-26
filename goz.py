#!/usr/bin/env python3

import math, os, random, shutil, sys, time

TARGET_FPS = 60
SHOW_FPS = True
RAMP = " .,:;-~=+*cxoXO0#%&@"
N1 = len(RAMP) - 1
IRIS_R = 0.45                      # iris yarıçapı (göz yarı-genişliği birimi)


# --------------------------------------------------------------- yardımcılar
def smooth(x):
    x = 0.0 if x < 0 else 1.0 if x > 1 else x
    return x * x * (3 - 2 * x)


def mix(a, b, w):
    return (a[0] + (b[0] - a[0]) * w, a[1] + (b[1] - a[1]) * w, a[2] + (b[2] - a[2]) * w)


def _h(ix, iy, seed):
    n = (ix * 374761393 + iy * 668265263 + seed * 1442695041) & 0xFFFFFFFF
    n = ((n ^ (n >> 13)) * 1274126177) & 0xFFFFFFFF
    return ((n ^ (n >> 16)) & 0xFFFF) / 65535.0


def vnoise(x, y, seed=0, px=0):
    ix, iy = math.floor(x), math.floor(y)
    fx, fy = x - ix, y - iy
    fx = fx * fx * (3 - 2 * fx)
    fy = fy * fy * (3 - 2 * fy)
    ix1 = ix + 1
    if px:
        ix %= px
        ix1 %= px
    a, b = _h(ix, iy, seed), _h(ix1, iy, seed)
    c, d = _h(ix, iy + 1, seed), _h(ix1, iy + 1, seed)
    return a + (b - a) * fx + (c - a) * fy + (a - b - c + d) * fx * fy


def fbm(x, y, seed=0, octaves=3):
    s, amp, tot = 0.0, 1.0, 0.0
    for o in range(octaves):
        s += amp * vnoise(x, y, seed + o * 7)
        tot += amp
        x *= 2.03
        y *= 2.03
        amp *= 0.5
    return s / tot


_CACHE = {}


def cell(r, g, b, dn=0.0):
    """Renk -> truecolor hücre (karakter yoğunluğu parlaklığı, renk tonu verir)."""
    r = 0 if r < 0 else 255 if r > 255 else int(r)
    g = 0 if g < 0 else 255 if g > 255 else int(g)
    b = 0 if b < 0 else 255 if b > 255 else int(b)
    lum = (77 * r + 150 * g + 29 * b) >> 8
    i = int((lum / 255.0) ** 0.8 * N1 + dn * 1.4 + 0.5)
    i = 0 if i < 0 else N1 if i > N1 else i
    key = ((r >> 3) << 15) | ((g >> 3) << 10) | ((b >> 3) << 5) | i
    s = _CACHE.get(key)
    if s is None:
        rq, gq, bq = min(255, ((r >> 3) << 3) + 4), min(255, ((g >> 3) << 3) + 4), min(255, ((b >> 3) << 3) + 4)
        s = "\033[38;2;%d;%d;%d;48;2;%d;%d;%dm%s" % (
            min(255, int(rq * 1.25)), min(255, int(gq * 1.25)), min(255, int(bq * 1.25)),
            int(rq * 0.34), int(gq * 0.34), int(bq * 0.34), RAMP[i])
        _CACHE[key] = s
    return s


def lash_cell(ch, bg):
    return "\033[38;2;26;16;13;48;2;%d;%d;%dm%s" % (int(bg[0] * 0.7), int(bg[1] * 0.7), int(bg[2] * 0.7), ch)


# --------------------------------------------------------------- iris dokusu
def _ramp(rn):
    stops = [(0.0, (205, 120, 12)), (0.30, (238, 172, 22)), (0.62, (252, 214, 54)),
             (0.85, (238, 198, 62)), (1.0, (150, 116, 30))]
    for (a, ca), (b, cb) in zip(stops, stops[1:]):
        if rn <= b:
            return mix(ca, cb, (rn - a) / (b - a))
    return stops[-1][1]


def make_iris_tex(NP=256, NRr=56):
    tex = []
    for j in range(NRr):
        rn = (j + 0.5) / NRr
        base = _ramp(rn)
        row = []
        for i in range(NP):
            ph = i / NP
            fib = 0.6 * vnoise(ph * 72, rn * 2.4, 11, 72) + 0.4 * vnoise(ph * 150, rn * 5.5, 12, 150)
            m = 0.60 + 0.90 * fib
            cpos = 0.30 + 0.035 * math.sin(ph * 6.2832 * 9) + 0.02 * math.sin(ph * 6.2832 * 5 + 1)
            m *= 1 + 0.38 * math.exp(-((rn - cpos) / 0.035) ** 2)            # collarette halkası
            m *= 1 - 0.30 * math.exp(-((rn - cpos - 0.07) / 0.025) ** 2)
            cn = vnoise(ph * 28, rn * 6, 13, 28)
            if 0.35 < rn < 0.92 and cn > 0.72:                                # kriptalar
                m *= 1 - 0.5 * min(1.0, (cn - 0.72) / 0.1)
            if rn > 0.82:                                                     # limbal halka
                m *= 1 - 0.78 * smooth((rn - 0.82) / 0.18)
            row.append((min(255, base[0] * m), min(255, base[1] * m), min(255, base[2] * m)))
        tex.append(row)
    return tex


# --------------------------------------------------------------- göz sahnesi
class Eye:
    def __init__(self, W, H):
        self.W, self.H = W, H
        self.HW = min(W * 0.42, H * 1.1)
        self.cx, self.cy = W / 2.0, H / 2.0
        s = 2.0 / self.HW
        self.X = [(c + 0.5 - self.cx) / self.HW for c in range(W)]
        self.Y = [(self.cy - (r + 0.5)) * s for r in range(H)]
        rg = random.Random(5)
        self.dith = [[rg.random() - 0.5 for _ in range(W)] for _ in range(H)]
        self.lash = [(rg.random() < 0.62, rg.uniform(0.05, 0.17), rg.random() < 0.18, rg.random() < 0.3) for _ in range(W)]
        self.tex = make_iris_tex()
        self._build_static()

    def _build_static(self):
        W, H, X, Y = self.W, self.H, self.X, self.Y
        self.SK = [[None] * W for _ in range(H)]
        self.SC = [[None] * W for _ in range(H)]
        self.static = []
        L = (-0.35, 0.50, 0.79)
        for r in range(H):
            y = Y[r]
            srow = []
            for c in range(W):
                x = X[c]
                # ---- cilt
                mott = fbm(x * 2.2 + 3, y * 2.2 + 7, 1, 3)
                pores = vnoise(x * 38, y * 38, 2)
                k = 0.88 + 0.20 * mott + 0.07 * (pores - 0.5)
                k *= 1 + 0.10 * (-x * 0.4 + y * 0.3)
                ue = math.exp(-((y + 0.46) / 0.17) ** 2) * max(0.0, 1 - (abs(x) / 1.15) ** 2)
                col = (226 * k * (1 - 0.10 * ue), 174 * k * (1 - 0.14 * ue), 146 * k * (1 - 0.05 * ue))
                yb = 0.84 - 0.14 * x * x + 0.08 * x                         # kaş
                tb = 0.085 * max(0.0, 1 - ((x + 0.25) / 1.35) ** 2) ** 0.7
                if tb > 0.006 and abs(y - yb) < tb:
                    dd = 1 - abs(y - yb) / tb
                    hair = fbm(x * 30, y * 12 + x * 8, 5, 2)
                    st = min(1.0, dd ** 0.6 * (0.55 + 0.9 * hair))
                    col = mix(col, (62, 40, 30), st * 0.92)
                self.SK[r][c] = col
                srow.append(cell(col[0], col[1], col[2], self.dith[r][c]))
                # ---- sklera (göz küresi)
                if abs(x) < 1.08 and abs(y) < 0.62:
                    Rb = 1.12
                    nz = math.sqrt(max(0.0, 1 - (x * x + y * y) / (Rb * Rb)))
                    dif = max(0.0, (x / Rb) * L[0] + (y / Rb) * L[1] + nz * L[2])
                    sh = 0.50 + 0.50 * dif ** 0.8
                    mo = 0.95 + 0.08 * fbm(x * 4 + 9, y * 4 + 2, 21, 2)
                    sc = (244 * sh * mo, 238 * sh * mo, 232 * sh * mo)
                    cr = smooth((abs(x) - 0.55) / 0.45)
                    sc = mix(sc, (232 * sh, 160 * sh, 150 * sh), 0.35 * cr)
                    if x < -0.80:                                           # gözyaşı kanalı (karunkül)
                        w = smooth((-0.80 - x) / 0.20)
                        sc = mix(sc, (222, 120, 114), 0.85 * w)
                    r1 = 1 - abs(2 * fbm(x * 5.5 + 11, y * 7 + 3, 31, 3) - 1)
                    r2 = 1 - abs(2 * fbm(x * 9 + 5, y * 5 + 8, 41, 3) - 1)
                    vein = max(smooth((r1 - 0.90) / 0.085), smooth((r2 - 0.92) / 0.07)) * (0.25 + 0.75 * cr)
                    sc = mix(sc, (178, 62, 60), 0.55 * vein)
                    self.SC[r][c] = sc
            self.static.append(srow)

    # göz kapağı eğrileri
    def lids(self, U0, L0, o):
        W = self.W
        yup, ylo = [0.0] * W, [0.0] * W
        for c, x in enumerate(self.X):
            if x <= -1 or x >= 1:
                yup[c] = ylo[c] = 0.10 * x
                continue
            w = 1 - x * x
            yu = U0 * w ** 0.8 * (1 - 0.18 * x) + 0.10 * x
            yl = -L0 * w ** 0.9 + 0.10 * x + 0.05 * (1 - o) * w ** 0.9
            yup[c] = yl + (yu - yl) * o
            ylo[c] = yl
        return yup, ylo

    def build_base(self, U0, L0, o):
        W, H, X, Y, HW = self.W, self.H, self.X, self.Y, self.HW
        k, cy = HW / 2.0, self.cy
        yup, ylo = self.lids(U0, L0, o)
        frame = [row[:] for row in self.static]
        top, bot = [1] * W, [0] * W
        dith, SK, SC = self.dith, self.SK, self.SC
        closed = o < 0.3
        for c in range(W):
            x, yu, yl = X[c], yup[c], ylo[c]
            if -1 < x < 1:
                first = int(math.floor(cy - 0.5 - yu * k)) + 1
                last = int(math.ceil(cy - 0.5 - yl * k)) - 1
            else:
                first, last = 1, 0
            top[c], bot[c] = first, last
            band_t = max(0, int(cy - 0.5 - (yu + 0.38) * k))
            band_b = min(H - 1, int(cy - 0.5 - (yl - 0.28) * k) + 1)
            crease = yu + 0.10 + 0.07 * o
            for r in range(band_t, band_b + 1):
                y = Y[r]
                if first <= r <= last:
                    sc = SC[r][c]
                    if sc is None:
                        continue
                    d, e = yu - y, y - yl
                    sf = 0.46 + 0.54 * smooth(d / 0.30)
                    if e < 0.10:
                        sf *= 0.78 + 0.22 * (e / 0.10)
                    if r == first:
                        sf *= 0.75
                    col = (sc[0] * sf, sc[1] * sf, sc[2] * sf)
                    if r == last:                                           # nemli alt kapak çizgisi
                        col = mix(col, (205, 112, 104), 0.55)
                    frame[r][c] = cell(col[0], col[1], col[2], dith[r][c])
                else:
                    sk = SK[r][c]
                    if y >= yu:
                        d, amp, above = y - yu, 0.32, True
                    else:
                        d, amp, above = yl - y, 0.20, False
                    ao = 1.0
                    if d < 0.30:
                        s = 1 - d / 0.30
                        ao = 1 - amp * s * s
                    f0, f1, f2 = ao, ao, ao
                    if above:
                        dc = abs(y - crease)
                        if dc < 0.04 and abs(x) < 1.15:
                            ln = (1 - dc / 0.04) * (1 - abs(x) / 1.5)
                            f0 = f1 = f2 = ao * (1 - 0.28 * ln)
                        if y < crease and abs(x) < 1.0:
                            f1 *= 0.95
                            f2 *= 0.94
                    if closed and -1 < x < 1 and (r == first or r == first - 1):
                        dk = 1 - 0.55 * (1 - o / 0.3)
                        f0 *= dk
                        f1 *= dk
                        f2 *= dk
                    frame[r][c] = cell(sk[0] * f0, sk[1] * f1, sk[2] * f2, dith[r][c])
            # kirpikler
            on, ln_, slant, low = self.lash[c]
            if -0.99 < x < 0.99:
                if on:
                    n = max(1, int(ln_ * (0.6 + 0.7 * smooth((x + 0.7) / 1.6)) * k * (0.55 + 0.45 * o)))
                    ch = "\\" if x < -0.5 else "/" if x > 0.3 else "|"
                    if slant:
                        ch = "|"
                    for i in range(n):
                        rr = (first + i) if closed else (first - 1 - i)
                        if 0 <= rr < H:
                            sk = SK[rr][c]
                            frame[rr][c] = lash_cell(ch, sk)
                if low and not closed and last + 1 < H:
                    frame[last + 1][c] = lash_cell("|", SK[last + 1][c])
        return frame, top, bot, yup, ylo

    # iris + gözbebeği + kornea yansıması (her karede)
    def overlay(self, frame, info, gx, gy, pr):
        _, top, bot, yup, ylo = info
        W, H, X, Y, HW = self.W, self.H, self.X, self.Y, self.HW
        k, cx, cy = HW / 2.0, self.cx, self.cy
        Cx, Cy = gx * 0.40, gy * 0.17
        a = IRIS_R * math.cos(gx * 0.6)
        b = IRIS_R * math.cos(gy * 0.35)
        c0 = max(0, int(cx + (Cx - a - 0.06) * HW))
        c1 = min(W - 1, int(cx + (Cx + a + 0.06) * HW) + 1)
        r0 = max(0, int(cy - 0.5 - (Cy + b + 0.06) * k))
        r1 = min(H - 1, int(cy - 0.5 - (Cy - b - 0.06) * k) + 1)
        tex, SC, dith = self.tex, self.SC, self.dith
        hx, hy = Cx * 0.7 - 0.17, Cy * 0.7 + 0.14           # pencere yansıması
        sx_, sy_ = Cx + 0.19, Cy - 0.20                     # ikinci küçük yansıma
        atan2, sqrt = math.atan2, math.sqrt
        inv_tau = 1 / 6.283185307
        for c in range(c0, c1 + 1):
            t0, t1 = top[c], bot[c]
            if t0 > t1:
                continue
            x = X[c]
            dx = (x - Cx) / a
            dx2 = dx * dx
            if dx2 > 1.25:
                continue
            yu, yl = yup[c], ylo[c]
            for r in range(max(r0, t0), min(r1, t1) + 1):
                y = Y[r]
                dy = (y - Cy) / b
                rho2 = dx2 + dy * dy
                if rho2 > 1.13:
                    continue
                rho = sqrt(rho2)
                d, e = yu - y, y - yl
                sf = 0.46 + 0.54 * smooth(d / 0.30)
                if e < 0.10:
                    sf *= 0.78 + 0.22 * (e / 0.10)
                if r == t0:
                    sf *= 0.75
                if rho < pr - 0.03:
                    R, G, B = 9, 7, 8
                else:
                    if rho < pr:
                        R, G, B = 9, 7, 8
                    else:
                        rn = (rho - pr) / (1 - pr)
                        j = int(rn * 55.99)
                        j = 55 if j > 55 else j
                        i = int(((atan2(dy, dx) * inv_tau) % 1.0) * 255.99)
                        R, G, B = tex[j][i]
                        gain = 1 + 0.22 * (dx * 0.6 - dy * 0.8) * rho
                        R, G, B = R * gain, G * gain, B * gain
                        if rho < pr + 0.03:                                 # gözbebeği kenar yumuşatma
                            w = (pr + 0.03 - rho) / 0.03
                            R, G, B = R + (9 - R) * w, G + (7 - G) * w, B + (8 - B) * w
                    R, G, B = R * sf, G * sf, B * sf
                    if rho > 0.96:                                          # iris -> sklera geçişi
                        sc = SC[r][c]
                        w = (rho - 0.96) / 0.10
                        w = 1.0 if w > 1 else w
                        R = R + (sc[0] * sf - R) * w
                        G = G + (sc[1] * sf - G) * w
                        B = B + (sc[2] * sf - B) * w
                if rho < pr - 0.03:
                    R, G, B = R * sf, G * sf, B * sf
                # --- kornea yansıması (pencere)
                ax, ay = abs(x - hx), abs(y - hy)
                if rho < 1.05 and ax < 0.20 and ay < 0.16:
                    if ax < 0.11 and ay < 0.075:
                        al = 0.35 if (ax < 0.012 or ay < 0.010) else 0.92
                        ed = min((0.11 - ax) / 0.02, (0.075 - ay) / 0.016, 1.0)
                        al *= ed
                        R, G, B = R + (255 - R) * al, G + (255 - G) * al, B + (255 - B) * al
                    gl = 1 - sqrt((ax / 0.22) ** 2 + (ay / 0.17) ** 2)
                    if gl > 0:
                        gl = 0.20 * gl * gl * 255
                        R, G, B = R + gl, G + gl, B + gl
                if rho < 1.0:
                    ddx, ddy = x - sx_, y - sy_
                    dd = ddx * ddx + ddy * ddy
                    if dd < 0.0012:
                        al = 0.55 * (1 - dd / 0.0012)
                        R, G, B = R + (255 - R) * al, G + (255 - G) * al, B + (255 - B) * al
                frame[r][c] = cell(R, G, B, dith[r][c])


# --------------------------------------------------------------- animasyon
class Anim:
    def __init__(self):
        self.r = random.Random()
        self.gx = self.gy = 0.0
        self.sx = self.sy = self.tx = self.ty = 0.0
        self.ts, self.dur, self.next = 0.0, 0.1, 0.8
        self.mode = "fix"
        self.pu_t = self.pu_end = 0.0
        self.p1 = self.p2 = 0.0
        self.blink_t = None
        self.next_blink = 1.8
        self.min_o = 0.0
        self.double = False
        self.last_blink_end = -9.0

    def update(self, t):
        r = self.r
        if self.mode == "pursuit":
            if t > self.pu_end:
                self.mode = "fix"
                self.sx, self.sy = self.gx, self.gy
                self.tx, self.ty = self.gx, self.gy
                self.ts, self.dur = t, 0.05
                self.next = t + r.uniform(0.4, 1.2)
            else:
                tt = t - self.pu_t
                kk = smooth(tt / 0.3)
                px = 0.75 * math.sin(0.9 * tt + self.p1)
                py = 0.30 * math.sin(1.5 * tt + self.p2)
                self.gx = self.sx + (px - self.sx) * kk
                self.gy = self.sy + (py - self.sy) * kk
        else:
            if t >= self.next:
                x = r.random()
                if x < 0.12:
                    self.mode = "pursuit"
                    self.pu_t, self.pu_end = t, t + r.uniform(1.8, 3.0)
                    self.sx, self.sy = self.gx, self.gy
                    self.p1, self.p2 = r.uniform(0, 6.28), r.uniform(0, 6.28)
                else:
                    if x < 0.30:
                        tx, ty = r.gauss(0, 0.08), r.gauss(0, 0.06)
                    else:
                        tx = max(-0.95, min(0.95, r.gauss(0, 0.55)))
                        ty = max(-0.6, min(0.6, r.gauss(0, 0.33)))
                    dist = math.hypot(tx - self.gx, (ty - self.gy) * 1.5)
                    self.sx, self.sy, self.tx, self.ty = self.gx, self.gy, tx, ty
                    self.ts, self.dur = t, 0.045 + 0.055 * dist
                    self.next = t + self.dur + r.uniform(0.5, 2.4)
                    if dist > 1.1 and r.random() < 0.4 and self.blink_t is None:
                        self.next_blink = min(self.next_blink, t + self.dur * 0.4)
            u = (t - self.ts) / self.dur
            e = smooth(u)
            self.gx = self.sx + (self.tx - self.sx) * e
            self.gy = self.sy + (self.ty - self.sy) * e
        gx = self.gx + 0.010 * math.sin(t * 17.3) + 0.006 * math.sin(t * 29.1 + 1)
        gy = self.gy + 0.008 * math.sin(t * 13.7 + 2)

        o = 1.0
        if self.blink_t is None and t >= self.next_blink:
            self.blink_t = t
            self.min_o = r.choice([0, 0, 0, 0, 0.2, 0.35])
            self.double = r.random() < 0.15
        if self.blink_t is not None:
            tb = t - self.blink_t
            if tb < 0.09:
                of = 1 - (tb / 0.09) ** 2
            elif tb < 0.13:
                of = 0.0
            elif tb < 0.38:
                u = (tb - 0.13) / 0.25
                of = 1 - (1 - u) ** 2
            else:
                of = 1.0
                self.blink_t = None
                self.last_blink_end = t
                self.next_blink = t + (0.30 if self.double else r.uniform(2.2, 5.8))
                self.double = False
            o = self.min_o + (1 - self.min_o) * of
        gy -= 0.30 * (1 - o)
        pr = 0.36 + 0.022 * math.sin(t * 1.1) + 0.014 * math.sin(t * 2.9 + 1.0)
        if t > self.last_blink_end:
            pr -= 0.05 * math.exp(-(t - self.last_blink_end) / 0.45)
        return gx, gy, o, pr


# --------------------------------------------------------------- ana döngü
def main():
    os.system("")                                          # Windows'ta ANSI/VT desteğini açar
    out = sys.stdout
    out.write("\033[?1049h\033[?25l\033[2J\033[HGöz hazırlanıyor...")
    out.flush()

    def size():
        cols, rows = shutil.get_terminal_size((120, 45))
        return min(cols, 150), min(rows - 1, 56)

    W, H = size()
    eye, anim = Eye(W, H), Anim()
    out.write("\033[2J")
    prev, base_key, info = None, None, None
    t0 = time.perf_counter()
    next_t = t0
    fps, fcount, fps_t = 0.0, 0, t0
    n = 0
    frame_dt = 1.0 / TARGET_FPS
    try:
        while True:
            now = time.perf_counter()
            t = now - t0
            n += 1
            if n % 30 == 0 and size() != (W, H):
                W, H = size()
                eye = Eye(W, H)
                prev, base_key = None, None
                out.write("\033[2J")
            gx, gy, o, pr = anim.update(t)
            U0 = 0.34 + 0.10 * gy
            L0 = 0.20 - 0.03 * gy
            key = (int(o * 300), int(U0 * 250), int(L0 * 250))
            if key != base_key:
                info = eye.build_base(U0, L0, o)
                base_key = key
            frame = [row[:] for row in info[0]]
            eye.overlay(frame, info, gx, gy, pr)

            fcount += 1
            if now - fps_t >= 0.5:
                fps, fcount, fps_t = fcount / (now - fps_t), 0, now
            if SHOW_FPS:
                for i, ch in enumerate(" %5.1f fps " % fps):
                    frame[H - 1][i] = "\033[38;2;210;210;210;48;2;0;0;0m" + ch

            buf = []
            if prev is None:
                for r in range(H):
                    buf.append("\033[%d;1H" % (r + 1))
                    buf.append("".join(frame[r]))
            else:
                for r in range(H):
                    fr, pv = frame[r], prev[r]
                    if fr == pv:
                        continue
                    f = 0
                    while fr[f] == pv[f]:
                        f += 1
                    l = W - 1
                    while fr[l] == pv[l]:
                        l -= 1
                    buf.append("\033[%d;%dH" % (r + 1, f + 1))
                    buf.append("".join(fr[f:l + 1]))
            if buf:
                buf.append("\033[0m")
                out.write("".join(buf))
                out.flush()
            prev = frame

            next_t += frame_dt
            now = time.perf_counter()
            if next_t < now - 0.1:
                next_t = now
            rem = next_t - now
            if rem > 0.004:
                time.sleep(rem - 0.003)
            while time.perf_counter() < next_t:
                pass
    except KeyboardInterrupt:
        pass
    finally:
        out.write("\033[0m\033[?25h\033[?1049l")
        out.flush()


if __name__ == "__main__":
    main()
