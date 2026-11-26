#!/usr/bin/env python3
"""
THE WORLD IN ONE DAY — WEDNESDAY 25 NOVEMBER 2026
Deterministic 1024x1024 newspaper-style infographic generator.
Pure Python 3 standard library (no external imaging libraries).
"""

import math
import os
import struct
import zlib

# =============================================================================
# SECTION 1: CONFIGURATION & COLOR PALETTE
# =============================================================================

WIDTH = 1024
HEIGHT = 1024
SUPERSAMPLE = 3

# Core newspaper palette (RGB tuples)
COLOR_PAPER = (247, 243, 233)       # Warm newsprint background
COLOR_PAPER_BAND = (234, 228, 214)  # Subtle header band tint
COLOR_INK = (20, 20, 25)            # Primary dark ink
COLOR_INK_MUTED = (82, 80, 76)      # Secondary caption/footer ink
COLOR_RED = (178, 34, 52)           # Editorial accent red
COLOR_BLUE = (30, 70, 140)          # Editorial accent blue
COLOR_RULE_LIGHT = (195, 188, 174)  # Subtle internal divider rule

# Editorial illustration palette (cohesive print-infographic tones)
COLOR_WHITE = (252, 250, 245)       # Crisp highlight / rocket body
COLOR_SILVER = (202, 206, 212)      # Metallic shading
COLOR_SKY_NIGHT = (22, 42, 84)      # Deep space blue
COLOR_SKY_TWILIGHT = (50, 84, 136)  # Upper atmosphere transition
COLOR_SKY_LIGHT = (228, 235, 242)   # Soft daylight sky tint
COLOR_SOLAR = (62, 124, 204)        # Space station solar panels
COLOR_ORANGE = (232, 108, 26)       # Flame mid-layer / container accent
COLOR_YELLOW = (246, 198, 52)       # Flame core / warning triangle fill
COLOR_SMOKE = (224, 220, 212)       # Light smoke puff
COLOR_SMOKE_DARK = (176, 172, 165)  # Smoke puff shadow
COLOR_GRID = (218, 212, 198)        # Subtle chart gridline
COLOR_WATER = (198, 214, 228)       # Subtle trade-water band
COLOR_SHIP_HULL = (42, 52, 66)      # Container ship hull silhouette
COLOR_SAND = (214, 196, 160)        # Low sand berm fill
COLOR_SAND_DARK = (162, 140, 102)   # Sand berm ridge & ground tone
COLOR_BARREL = (72, 88, 104)        # Steel drum body
COLOR_BARREL_LIGHT = (108, 126, 144)  # Steel drum top / highlight
COLOR_BARREL_DARK = (48, 60, 74)    # Steel drum shadow side
COLOR_DUST_DARK = (130, 130, 128)   # Dust plume shadow layer
COLOR_DUST_MID = (168, 167, 164)    # Dust plume body
COLOR_DUST_LIGHT = (206, 205, 200)  # Dust plume highlight

# Page margins and layout regions (all coordinates in pixels)
MARGIN_X = 38
CONTENT_X0 = MARGIN_X
CONTENT_X1 = WIDTH - MARGIN_X
CONTENT_W = CONTENT_X1 - CONTENT_X0  # 948 px

# Masthead region
MASTHEAD_TOP_Y = 26
MASTHEAD_RULE_Y = 150

# Top 3-panel row geometry: 3 equal boxes of 304 px + two 18 px gaps = 948 px
PANEL_GAP = 18
PANEL_COUNT = 3
PANEL_W = (CONTENT_W - PANEL_GAP * (PANEL_COUNT - 1)) // PANEL_COUNT  # 304 px
PANEL_Y = 170
PANEL_H = 352
PANEL_HEADER_H = 30

# Lower section vertical anchors (between PANEL_Y + PANEL_H = 522 and FOOTER_RULE_Y = 965)
NUMBERS_HEADER_Y = 533
NUMBERS_GRID_Y = 553
NUMBERS_ROW_H = 61
NUMBERS_GRID_H = NUMBERS_ROW_H * 2  # 122 px -> ends at 675

MORE_HEADER_Y = 686
MORE_BODY_Y = 706

BRIEF_HEADER_Y = 852
BRIEF_BODY_Y = 872

# Two-column layout geometry for lower sections
TWO_COL_GAP = 24
TWO_COL_W = (CONTENT_W - TWO_COL_GAP) // 2  # 462 px
TWO_COL_DIV_X = CONTENT_X0 + TWO_COL_W + TWO_COL_GAP // 2  # 512 px

# Footer region
FOOTER_RULE_Y = 965
FOOTER_TEXT_Y = 979


# =============================================================================
# SECTION 2: RGB FRAMEBUFFER & DRAWING PRIMITIVES
# =============================================================================

class Canvas:
    """In-memory RGB framebuffer with supersampled 2D raster drawing primitives."""

    def __init__(self, width, height, bg_color=COLOR_PAPER, ss=1):
        self.out_width = int(width)
        self.out_height = int(height)
        self.ss = max(1, int(ss))
        self.width = self.out_width * self.ss
        self.height = self.out_height * self.ss
        r, g, b = bg_color
        self.buf = bytearray(bytes((r, g, b)) * (self.width * self.height))

    def set_pixel(self, x, y, color):
        """Set a single pixel in buffer coordinates if within canvas bounds."""
        ix = int(x)
        iy = int(y)
        if 0 <= ix < self.width and 0 <= iy < self.height:
            idx = (iy * self.width + ix) * 3
            self.buf[idx] = color[0]
            self.buf[idx + 1] = color[1]
            self.buf[idx + 2] = color[2]

    def blend_pixel(self, x, y, color, alpha):
        """Alpha-blend a color onto a buffer pixel (alpha in [0.0, 1.0])."""
        if alpha <= 0.0:
            return
        if alpha >= 1.0:
            self.set_pixel(x, y, color)
            return
        ix = int(x)
        iy = int(y)
        if 0 <= ix < self.width and 0 <= iy < self.height:
            idx = (iy * self.width + ix) * 3
            inv = 1.0 - alpha
            self.buf[idx] = int(self.buf[idx] * inv + color[0] * alpha + 0.5)
            self.buf[idx + 1] = int(self.buf[idx + 1] * inv + color[1] * alpha + 0.5)
            self.buf[idx + 2] = int(self.buf[idx + 2] * inv + color[2] * alpha + 0.5)

    def fill_rect(self, x, y, w, h, color):
        """Fill an axis-aligned rectangle clipped to canvas bounds."""
        ss = self.ss
        x0 = max(0, int(round(x * ss)))
        y0 = max(0, int(round(y * ss)))
        x1 = min(self.width, int(round((x + w) * ss)))
        y1 = min(self.height, int(round((y + h) * ss)))
        if x1 <= x0 or y1 <= y0:
            return
        span = x1 - x0
        row_bytes = bytes((color[0], color[1], color[2])) * span
        stride = self.width * 3
        row_start = x0 * 3
        row_end = x1 * 3
        buf = self.buf
        for py in range(y0, y1):
            base = py * stride
            buf[base + row_start:base + row_end] = row_bytes

    def stroke_rect(self, x, y, w, h, color, thickness=1):
        """Draw an axis-aligned rectangle outline with inward-aligned thickness."""
        t = float(thickness)
        self.fill_rect(x, y, w, t, color)
        self.fill_rect(x, y + h - t, w, t, color)
        self.fill_rect(x, y, t, h, color)
        self.fill_rect(x + w - t, y, t, h, color)

    def draw_line(self, x0, y0, x1, y1, color, thickness=1.0):
        """Draw a line segment with rounded caps and smooth distance-based thickness."""
        orig_x0 = float(x0)
        orig_y0 = float(y0)
        ss = float(self.ss)
        x0 = orig_x0 * ss
        y0 = orig_y0 * ss
        x1 = float(x1) * ss
        y1 = float(y1) * ss
        dx = x1 - x0
        dy = y1 - y0
        seg_len_sq = dx * dx + dy * dy
        r_logical = max(0.5, float(thickness) * 0.5)
        if seg_len_sq < 1e-9:
            self.fill_circle(orig_x0, orig_y0, r_logical, color)
            return

        r = max(0.5, float(thickness) * ss * 0.5)
        r_outer = r + 0.5
        r_inner = max(0.0, r - 0.5)
        seg_len = math.sqrt(seg_len_sq)

        y_min = max(0, int(math.floor(min(y0, y1) - r_outer)))
        y_max = min(self.height - 1, int(math.ceil(max(y0, y1) + r_outer)))
        x_clamp_min = max(0, int(math.floor(min(x0, x1) - r_outer)))
        x_clamp_max = min(self.width - 1, int(math.ceil(max(x0, x1) + r_outer)))

        abs_dy = abs(dy)
        inv_len_sq = 1.0 / seg_len_sq
        r_outer_sq = r_outer * r_outer
        r_inner_sq = r_inner * r_inner

        if abs_dy > 1e-6:
            slope_x = dx / dy
            half_band = r_outer * seg_len / abs_dy + 1.0
        else:
            slope_x = 0.0
            half_band = 0.0

        buf = self.buf
        stride = self.width * 3
        cr, cg, cb = color
        sqrt = math.sqrt

        for py in range(y_min, y_max + 1):
            if abs_dy > 1e-6:
                cx = x0 + (py - y0) * slope_x
                rx0 = max(x_clamp_min, int(math.floor(cx - half_band)))
                rx1 = min(x_clamp_max, int(math.ceil(cx + half_band)))
            else:
                rx0 = x_clamp_min
                rx1 = x_clamp_max

            vy = py - y0
            row_base = py * stride
            for px in range(rx0, rx1 + 1):
                vx = px - x0
                t = (vx * dx + vy * dy) * inv_len_sq
                if t < 0.0:
                    t = 0.0
                elif t > 1.0:
                    t = 1.0
                proj_x = vx - t * dx
                proj_y = vy - t * dy
                d2 = proj_x * proj_x + proj_y * proj_y
                if d2 <= r_inner_sq:
                    idx = row_base + px * 3
                    buf[idx] = cr
                    buf[idx + 1] = cg
                    buf[idx + 2] = cb
                elif d2 < r_outer_sq:
                    alpha = r_outer - sqrt(d2)
                    inv = 1.0 - alpha
                    idx = row_base + px * 3
                    buf[idx] = int(buf[idx] * inv + cr * alpha + 0.5)
                    buf[idx + 1] = int(buf[idx + 1] * inv + cg * alpha + 0.5)
                    buf[idx + 2] = int(buf[idx + 2] * inv + cb * alpha + 0.5)

    def draw_dashed_line(self, x0, y0, x1, y1, color, thickness=1.0, dash_len=8.0, gap_len=5.0):
        """Draw a dashed line segment from (x0, y0) to (x1, y1)."""
        x0 = float(x0)
        y0 = float(y0)
        x1 = float(x1)
        y1 = float(y1)
        dx = x1 - x0
        dy = y1 - y0
        total_len = math.hypot(dx, dy)
        if total_len < 1e-6:
            self.fill_circle(x0, y0, max(0.5, thickness * 0.5), color)
            return
        ux = dx / total_len
        uy = dy / total_len
        step = max(1.0, float(dash_len)) + max(1.0, float(gap_len))
        pos = 0.0
        while pos < total_len:
            end = min(total_len, pos + dash_len)
            self.draw_line(
                x0 + ux * pos,
                y0 + uy * pos,
                x0 + ux * end,
                y0 + uy * end,
                color,
                thickness=thickness,
            )
            pos += step

    def fill_circle(self, cx, cy, radius, color):
        """Draw a filled circle with smooth edges."""
        ss = float(self.ss)
        cx = float(cx) * ss
        cy = float(cy) * ss
        r = float(radius) * ss
        if r <= 0.0:
            return
        r_outer = r + 0.5
        r_inner = max(0.0, r - 0.5)
        r_outer_sq = r_outer * r_outer
        r_inner_sq = r_inner * r_inner

        y0 = max(0, int(math.floor(cy - r_outer)))
        y1 = min(self.height - 1, int(math.ceil(cy + r_outer)))
        x0 = max(0, int(math.floor(cx - r_outer)))
        x1 = min(self.width - 1, int(math.ceil(cx + r_outer)))

        buf = self.buf
        stride = self.width * 3
        cr, cg, cb = color
        sqrt = math.sqrt

        for py in range(y0, y1 + 1):
            dy = py - cy
            dy2 = dy * dy
            if dy2 > r_outer_sq:
                continue
            max_dx = sqrt(r_outer_sq - dy2)
            rx0 = max(x0, int(math.floor(cx - max_dx)))
            rx1 = min(x1, int(math.ceil(cx + max_dx)))
            row_base = py * stride
            for px in range(rx0, rx1 + 1):
                dx = px - cx
                d2 = dx * dx + dy2
                if d2 <= r_inner_sq:
                    idx = row_base + px * 3
                    buf[idx] = cr
                    buf[idx + 1] = cg
                    buf[idx + 2] = cb
                elif d2 < r_outer_sq:
                    alpha = r_outer - sqrt(d2)
                    inv = 1.0 - alpha
                    idx = row_base + px * 3
                    buf[idx] = int(buf[idx] * inv + cr * alpha + 0.5)
                    buf[idx + 1] = int(buf[idx + 1] * inv + cg * alpha + 0.5)
                    buf[idx + 2] = int(buf[idx + 2] * inv + cb * alpha + 0.5)

    def stroke_circle(self, cx, cy, radius, color, thickness=1.0):
        """Draw an outlined circle centered at (cx, cy)."""
        ss = float(self.ss)
        cx = float(cx) * ss
        cy = float(cy) * ss
        r = float(radius) * ss
        if r <= 0.0:
            return
        half_t = max(0.5, float(thickness) * ss * 0.5)
        outer = r + half_t + 0.5
        inner_cut = max(0.0, r - half_t - 0.5)

        y0 = max(0, int(math.floor(cy - outer)))
        y1 = min(self.height - 1, int(math.ceil(cy + outer)))
        x0 = max(0, int(math.floor(cx - outer)))
        x1 = min(self.width - 1, int(math.ceil(cx + outer)))

        outer_sq = outer * outer
        inner_cut_sq = inner_cut * inner_cut
        solid_half = max(0.0, half_t - 0.5)
        fade_half = half_t + 0.5

        buf = self.buf
        stride = self.width * 3
        cr, cg, cb = color
        sqrt = math.sqrt

        for py in range(y0, y1 + 1):
            dy = py - cy
            dy2 = dy * dy
            if dy2 > outer_sq:
                continue
            max_dx = sqrt(outer_sq - dy2)
            rx0 = max(x0, int(math.floor(cx - max_dx)))
            rx1 = min(x1, int(math.ceil(cx + max_dx)))
            row_base = py * stride
            for px in range(rx0, rx1 + 1):
                dx = px - cx
                d2 = dx * dx + dy2
                if d2 > outer_sq or d2 < inner_cut_sq:
                    continue
                dist_ring = abs(sqrt(d2) - r)
                if dist_ring <= solid_half:
                    idx = row_base + px * 3
                    buf[idx] = cr
                    buf[idx + 1] = cg
                    buf[idx + 2] = cb
                elif dist_ring < fade_half:
                    alpha = fade_half - dist_ring
                    inv = 1.0 - alpha
                    idx = row_base + px * 3
                    buf[idx] = int(buf[idx] * inv + cr * alpha + 0.5)
                    buf[idx + 1] = int(buf[idx + 1] * inv + cg * alpha + 0.5)
                    buf[idx + 2] = int(buf[idx + 2] * inv + cb * alpha + 0.5)

    def draw_circle(self, cx, cy, radius, color, fill=True, thickness=1.0):
        """Draw either a filled or outlined circle."""
        if fill:
            self.fill_circle(cx, cy, radius, color)
        else:
            self.stroke_circle(cx, cy, radius, color, thickness=thickness)

    def fill_polygon(self, points, color):
        """Fill an arbitrary polygon using scanline even-odd rasterization."""
        n = len(points)
        if n < 3:
            return
        ss = float(self.ss)
        pts = [(p[0] * ss, p[1] * ss) for p in points]
        ys = [p[1] for p in pts]
        y_min = max(0, int(math.floor(min(ys))))
        y_max = min(self.height - 1, int(math.ceil(max(ys))))
        stride = self.width * 3
        buf = self.buf
        px_bytes = bytes((color[0], color[1], color[2]))

        for py in range(y_min, y_max + 1):
            sy = py + 0.5
            intersections = []
            j = n - 1
            for i in range(n):
                x1, y1 = pts[j]
                x2, y2 = pts[i]
                if (y1 <= sy < y2) or (y2 <= sy < y1):
                    ix = x1 + (sy - y1) * (x2 - x1) / (y2 - y1)
                    intersections.append(ix)
                j = i
            if not intersections:
                continue
            intersections.sort()
            base = py * stride
            for k in range(0, len(intersections) - 1, 2):
                x_start = max(0, int(math.ceil(intersections[k] - 0.5)))
                x_end = min(self.width - 1, int(math.floor(intersections[k + 1] - 0.5)))
                if x_end >= x_start:
                    span = x_end - x_start + 1
                    buf[base + x_start * 3:base + (x_end + 1) * 3] = px_bytes * span

    def stroke_polygon(self, points, color, thickness=1.0, closed=True):
        """Draw the outline of a polygon or open polyline."""
        n = len(points)
        if n < 2:
            return
        limit = n if closed else n - 1
        for i in range(limit):
            x0, y0 = points[i]
            x1, y1 = points[(i + 1) % n]
            self.draw_line(x0, y0, x1, y1, color, thickness=thickness)

    def draw_text(self, x, y, text, scale, color, thickness=None, align="left", letter_spacing=None):
        """Render stroke-font text onto this canvas."""
        sp = LETTER_SPACING if letter_spacing is None else letter_spacing
        draw_text(self, x, y, text, scale, color, thickness=thickness, align=align, letter_spacing=sp)

    def downsample(self):
        """Downsample supersampled buffer by box-averaging ss x ss blocks into a 1x Canvas."""
        ss = self.ss
        if ss <= 1:
            return self
        out_w = self.out_width
        out_h = self.out_height
        out_canvas = Canvas(out_w, out_h, ss=1)
        out_buf = out_canvas.buf
        src_buf = self.buf
        src_stride = self.width * 3
        out_stride = out_w * 3
        step = ss * 3
        area = ss * ss
        half = area // 2

        if ss == 3:
            for y in range(out_h):
                b0 = (y * 3) * src_stride
                b1 = b0 + src_stride
                b2 = b1 + src_stride
                r0 = src_buf[b0:b0 + src_stride]
                r1 = src_buf[b1:b1 + src_stride]
                r2 = src_buf[b2:b2 + src_stride]
                out_row = y * out_stride
                for ch in range(3):
                    out_buf[out_row + ch:out_row + out_stride:3] = bytes(
                        (a + b + c + d + e + f + g + h + i + 4) // 9
                        for a, b, c, d, e, f, g, h, i in zip(
                            r0[ch::9], r0[ch + 3::9], r0[ch + 6::9],
                            r1[ch::9], r1[ch + 3::9], r1[ch + 6::9],
                            r2[ch::9], r2[ch + 3::9], r2[ch + 6::9],
                        )
                    )
        elif ss == 2:
            for y in range(out_h):
                b0 = (y * 2) * src_stride
                b1 = b0 + src_stride
                r0 = src_buf[b0:b0 + src_stride]
                r1 = src_buf[b1:b1 + src_stride]
                out_row = y * out_stride
                for ch in range(3):
                    out_buf[out_row + ch:out_row + out_stride:3] = bytes(
                        (a + b + c + d + 2) >> 2
                        for a, b, c, d in zip(
                            r0[ch::6], r0[ch + 3::6],
                            r1[ch::6], r1[ch + 3::6],
                        )
                    )
        else:
            for y in range(out_h):
                sy0 = y * ss
                out_row = y * out_stride
                for x in range(out_w):
                    sx0 = x * ss
                    sr = sg = sb = 0
                    for dy in range(ss):
                        row_off = (sy0 + dy) * src_stride + sx0 * 3
                        for dx in range(ss):
                            idx = row_off + dx * 3
                            sr += src_buf[idx]
                            sg += src_buf[idx + 1]
                            sb += src_buf[idx + 2]
                    oidx = out_row + x * 3
                    out_buf[oidx] = (sr + half) // area
                    out_buf[oidx + 1] = (sg + half) // area
                    out_buf[oidx + 2] = (sb + half) // area
        return out_canvas


# =============================================================================
# SECTION 3: STROKE FONT & TEXT LAYOUT
# =============================================================================

# Hand-written polyline glyphs on a 5-wide x 7-tall coordinate grid.
# Each entry maps character -> (advance_width, list_of_polylines).
GLYPH_HEIGHT = 7.0
LETTER_SPACING = 1.5

FONT_GLYPHS = {
    # Uppercase letters A-Z
    "A": (5.0, [
        [(0.0, 7.0), (2.5, 0.0), (5.0, 7.0)],
        [(0.9, 4.7), (4.1, 4.7)],
    ]),
    "B": (4.6, [
        [(0.0, 7.0), (0.0, 0.0), (3.0, 0.0), (4.0, 0.6), (4.3, 1.6),
         (3.9, 2.7), (2.9, 3.3), (0.0, 3.3)],
        [(2.9, 3.3), (4.1, 3.9), (4.6, 5.1), (4.1, 6.3), (3.1, 7.0), (0.0, 7.0)],
    ]),
    "C": (4.6, [
        [(4.5, 1.3), (3.7, 0.3), (2.4, 0.0), (1.1, 0.5), (0.2, 1.8),
         (0.0, 3.5), (0.2, 5.2), (1.1, 6.5), (2.4, 7.0), (3.7, 6.7), (4.5, 5.7)],
    ]),
    "D": (4.8, [
        [(0.0, 7.0), (0.0, 0.0), (2.4, 0.0), (3.7, 0.6), (4.5, 1.8),
         (4.8, 3.5), (4.5, 5.2), (3.7, 6.4), (2.4, 7.0), (0.0, 7.0)],
    ]),
    "E": (4.2, [
        [(4.2, 0.0), (0.0, 0.0), (0.0, 7.0), (4.2, 7.0)],
        [(0.0, 3.4), (3.4, 3.4)],
    ]),
    "F": (4.0, [
        [(4.0, 0.0), (0.0, 0.0), (0.0, 7.0)],
        [(0.0, 3.4), (3.3, 3.4)],
    ]),
    "G": (4.8, [
        [(4.6, 1.3), (3.8, 0.3), (2.5, 0.0), (1.1, 0.5), (0.2, 1.8),
         (0.0, 3.5), (0.2, 5.2), (1.1, 6.5), (2.5, 7.0), (3.8, 6.6),
         (4.7, 5.6), (4.7, 3.7), (2.7, 3.7)],
    ]),
    "H": (4.6, [
        [(0.0, 0.0), (0.0, 7.0)],
        [(4.6, 0.0), (4.6, 7.0)],
        [(0.0, 3.4), (4.6, 3.4)],
    ]),
    "I": (2.4, [
        [(0.2, 0.0), (2.2, 0.0)],
        [(1.2, 0.0), (1.2, 7.0)],
        [(0.2, 7.0), (2.2, 7.0)],
    ]),
    "J": (4.0, [
        [(1.2, 0.0), (4.0, 0.0)],
        [(3.2, 0.0), (3.2, 5.2), (2.7, 6.4), (1.7, 7.0), (0.7, 6.6), (0.0, 5.5)],
    ]),
    "K": (4.6, [
        [(0.0, 0.0), (0.0, 7.0)],
        [(4.4, 0.0), (0.0, 4.0)],
        [(1.6, 2.6), (4.6, 7.0)],
    ]),
    "L": (4.0, [
        [(0.0, 0.0), (0.0, 7.0), (4.0, 7.0)],
    ]),
    "M": (5.0, [
        [(0.0, 7.0), (0.0, 0.0), (2.5, 4.4), (5.0, 0.0), (5.0, 7.0)],
    ]),
    "N": (4.6, [
        [(0.0, 7.0), (0.0, 0.0), (4.6, 7.0), (4.6, 0.0)],
    ]),
    "O": (4.8, [
        [(2.4, 0.0), (3.7, 0.4), (4.5, 1.6), (4.8, 3.5), (4.5, 5.4),
         (3.7, 6.6), (2.4, 7.0), (1.1, 6.6), (0.3, 5.4), (0.0, 3.5),
         (0.3, 1.6), (1.1, 0.4), (2.4, 0.0)],
    ]),
    "P": (4.5, [
        [(0.0, 7.0), (0.0, 0.0), (3.0, 0.0), (4.1, 0.6), (4.5, 1.8),
         (4.1, 3.0), (3.0, 3.6), (0.0, 3.6)],
    ]),
    "Q": (4.8, [
        [(2.4, 0.0), (3.7, 0.4), (4.5, 1.6), (4.8, 3.5), (4.5, 5.4),
         (3.7, 6.6), (2.4, 7.0), (1.1, 6.6), (0.3, 5.4), (0.0, 3.5),
         (0.3, 1.6), (1.1, 0.4), (2.4, 0.0)],
        [(2.9, 5.2), (4.8, 7.3)],
    ]),
    "R": (4.6, [
        [(0.0, 7.0), (0.0, 0.0), (3.0, 0.0), (4.1, 0.6), (4.5, 1.8),
         (4.1, 3.0), (3.0, 3.6), (0.0, 3.6)],
        [(2.4, 3.6), (4.6, 7.0)],
    ]),
    "S": (4.5, [
        [(4.3, 1.2), (3.5, 0.3), (2.2, 0.0), (1.0, 0.4), (0.2, 1.3),
         (0.4, 2.4), (1.4, 3.1), (3.2, 3.7), (4.2, 4.5), (4.5, 5.5),
         (3.9, 6.5), (2.5, 7.0), (1.1, 6.7), (0.1, 5.8)],
    ]),
    "T": (4.6, [
        [(0.0, 0.0), (4.6, 0.0)],
        [(2.3, 0.0), (2.3, 7.0)],
    ]),
    "U": (4.6, [
        [(0.0, 0.0), (0.0, 5.0), (0.5, 6.2), (1.5, 6.9), (2.3, 7.0),
         (3.1, 6.9), (4.1, 6.2), (4.6, 5.0), (4.6, 0.0)],
    ]),
    "V": (4.8, [
        [(0.0, 0.0), (2.4, 7.0), (4.8, 0.0)],
    ]),
    "W": (5.0, [
        [(0.0, 0.0), (1.1, 7.0), (2.5, 2.4), (3.9, 7.0), (5.0, 0.0)],
    ]),
    "X": (4.6, [
        [(0.0, 0.0), (4.6, 7.0)],
        [(4.6, 0.0), (0.0, 7.0)],
    ]),
    "Y": (4.6, [
        [(0.0, 0.0), (2.3, 3.6), (4.6, 0.0)],
        [(2.3, 3.6), (2.3, 7.0)],
    ]),
    "Z": (4.4, [
        [(0.0, 0.0), (4.4, 0.0), (0.0, 7.0), (4.4, 7.0)],
    ]),

    # Digits 0-9
    "0": (4.4, [
        [(2.2, 0.0), (3.4, 0.5), (4.2, 1.8), (4.4, 3.5), (4.2, 5.2),
         (3.4, 6.5), (2.2, 7.0), (1.0, 6.5), (0.2, 5.2), (0.0, 3.5),
         (0.2, 1.8), (1.0, 0.5), (2.2, 0.0)],
    ]),
    "1": (3.4, [
        [(0.5, 1.3), (1.8, 0.0), (1.8, 7.0)],
        [(0.3, 7.0), (3.1, 7.0)],
    ]),
    "2": (4.5, [
        [(0.2, 1.6), (0.9, 0.5), (2.2, 0.0), (3.5, 0.4), (4.3, 1.4),
         (4.3, 2.6), (3.5, 3.7), (0.0, 7.0), (4.5, 7.0)],
    ]),
    "3": (4.4, [
        [(0.3, 1.1), (1.1, 0.2), (2.3, 0.0), (3.6, 0.5), (4.2, 1.5),
         (3.9, 2.6), (2.9, 3.3), (1.7, 3.3)],
        [(2.9, 3.3), (4.0, 4.0), (4.4, 5.2), (3.8, 6.4), (2.4, 7.0),
         (1.0, 6.7), (0.1, 5.8)],
    ]),
    "4": (4.6, [
        [(3.4, 7.0), (3.4, 0.0), (0.0, 4.8), (4.6, 4.8)],
    ]),
    "5": (4.4, [
        [(4.1, 0.0), (0.6, 0.0), (0.3, 3.2), (1.4, 2.5), (2.7, 2.5),
         (3.9, 3.2), (4.4, 4.5), (4.0, 6.0), (2.9, 6.9), (1.4, 7.0), (0.2, 6.1)],
    ]),
    "6": (4.5, [
        [(4.0, 0.9), (3.1, 0.1), (1.9, 0.0), (0.8, 0.8), (0.1, 2.4),
         (0.0, 4.5), (0.5, 6.1), (1.5, 6.9), (2.7, 7.0), (3.9, 6.3),
         (4.5, 5.1), (4.1, 3.8), (3.1, 3.0), (1.8, 2.9), (0.6, 3.5), (0.1, 4.5)],
    ]),
    "7": (4.4, [
        [(0.0, 0.0), (4.4, 0.0), (1.6, 7.0)],
    ]),
    "8": (4.5, [
        [(2.25, 3.3), (1.1, 2.9), (0.4, 2.0), (0.5, 0.9), (1.3, 0.2),
         (2.25, 0.0), (3.2, 0.2), (4.0, 0.9), (4.1, 2.0), (3.4, 2.9),
         (2.25, 3.3), (3.6, 3.9), (4.4, 4.9), (4.3, 6.0), (3.4, 6.8),
         (2.25, 7.0), (1.1, 6.8), (0.2, 6.0), (0.1, 4.9), (0.9, 3.9), (2.25, 3.3)],
    ]),
    "9": (4.5, [
        [(4.4, 2.5), (3.9, 3.5), (2.7, 4.1), (1.4, 4.0), (0.4, 3.2),
         (0.0, 1.9), (0.6, 0.7), (1.8, 0.0), (3.0, 0.1), (4.0, 0.9),
         (4.5, 2.5), (4.4, 4.6), (3.7, 6.2), (2.6, 7.0), (1.4, 6.9), (0.5, 6.1)],
    ]),

    # Punctuation and space
    " ": (2.8, []),
    ".": (1.4, [
        [(0.7, 6.4), (0.7, 7.0)],
    ]),
    ",": (1.6, [
        [(0.9, 6.3), (0.9, 7.0), (0.3, 8.0)],
    ]),
    ":": (1.4, [
        [(0.7, 2.2), (0.7, 2.8)],
        [(0.7, 6.4), (0.7, 7.0)],
    ]),
    ";": (1.6, [
        [(0.9, 2.2), (0.9, 2.8)],
        [(0.9, 6.3), (0.9, 7.0), (0.3, 8.0)],
    ]),
    "'": (1.4, [
        [(0.8, 0.0), (0.6, 1.8)],
    ]),
    "-": (3.2, [
        [(0.2, 3.6), (3.0, 3.6)],
    ]),
    "$": (4.6, [
        [(4.2, 1.4), (3.4, 0.7), (2.3, 0.5), (1.1, 0.8), (0.4, 1.6),
         (0.6, 2.6), (1.5, 3.2), (3.1, 3.7), (4.1, 4.4), (4.3, 5.4),
         (3.6, 6.2), (2.3, 6.5), (1.1, 6.2), (0.3, 5.5)],
        [(2.3, -0.4), (2.3, 7.4)],
    ]),
    "%": (4.8, [
        [(0.4, 6.8), (4.4, 0.2)],
        [(1.1, 0.4), (1.8, 0.8), (1.8, 1.7), (1.1, 2.1),
         (0.4, 1.7), (0.4, 0.8), (1.1, 0.4)],
        [(3.7, 4.9), (4.4, 5.3), (4.4, 6.2), (3.7, 6.6),
         (3.0, 6.2), (3.0, 5.3), (3.7, 4.9)],
    ]),
    "+": (4.2, [
        [(0.2, 3.5), (4.0, 3.5)],
        [(2.1, 1.5), (2.1, 5.5)],
    ]),
    "/": (3.6, [
        [(0.2, 7.0), (3.4, 0.0)],
    ]),
    "(": (2.4, [
        [(2.1, 0.0), (1.1, 1.2), (0.5, 3.5), (1.1, 5.8), (2.1, 7.0)],
    ]),
    ")": (2.4, [
        [(0.3, 0.0), (1.3, 1.2), (1.9, 3.5), (1.3, 5.8), (0.3, 7.0)],
    ]),
    "!": (1.6, [
        [(0.8, 0.0), (0.8, 4.8)],
        [(0.8, 6.4), (0.8, 7.0)],
    ]),
    "?": (4.2, [
        [(0.3, 1.4), (1.0, 0.4), (2.2, 0.0), (3.5, 0.5), (4.0, 1.6),
         (3.6, 2.7), (2.6, 3.5), (2.1, 4.2), (2.1, 5.0)],
        [(2.1, 6.4), (2.1, 7.0)],
    ]),
    "&": (4.8, [
        [(4.6, 7.0), (0.8, 2.3), (0.6, 1.2), (1.2, 0.3), (2.2, 0.0),
         (3.1, 0.4), (3.4, 1.3), (2.9, 2.2), (0.7, 3.9), (0.1, 5.0),
         (0.5, 6.2), (1.6, 6.9), (2.9, 6.7), (4.0, 5.6), (4.6, 4.1)],
    ]),
}


def _lookup_glyph(ch):
    """Return (advance_width, strokes) for a character (falling back to space)."""
    if ch in FONT_GLYPHS:
        return FONT_GLYPHS[ch]
    up = ch.upper()
    if up in FONT_GLYPHS:
        return FONT_GLYPHS[up]
    return FONT_GLYPHS[" "]


def text_width(text, scale, thickness=None, letter_spacing=LETTER_SPACING):
    """Compute the pixel width of a single line of text at the given scale."""
    if not text:
        return 0.0
    t = max(1.0, scale * 0.85) if thickness is None else float(thickness)
    total_units = 0.0
    for idx, ch in enumerate(text):
        adv, _ = _lookup_glyph(ch)
        total_units += adv
        if idx < len(text) - 1:
            total_units += letter_spacing
    return total_units * scale + t


def text_height(scale, thickness=None):
    """Compute the pixel height of a single line of text at the given scale."""
    t = max(1.0, scale * 0.85) if thickness is None else float(thickness)
    return GLYPH_HEIGHT * scale + t


def wrap_text(text, max_width, scale, thickness=None, letter_spacing=LETTER_SPACING):
    """Split text into lines that each fit within max_width pixels at scale."""
    lines = []
    for paragraph in text.split("\n"):
        words = paragraph.split()
        if not words:
            lines.append("")
            continue
        current = ""
        for word in words:
            candidate = word if not current else current + " " + word
            if text_width(candidate, scale, thickness, letter_spacing) <= max_width:
                current = candidate
            else:
                if current:
                    lines.append(current)
                    current = ""
                if text_width(word, scale, thickness, letter_spacing) <= max_width:
                    current = word
                else:
                    # Break an overlong word character by character
                    piece = ""
                    for ch in word:
                        test_piece = piece + ch
                        if piece and text_width(test_piece, scale, thickness, letter_spacing) > max_width:
                            lines.append(piece)
                            piece = ch
                        else:
                            piece = test_piece
                    current = piece
        if current:
            lines.append(current)
    return lines


def draw_text(canvas, x, y, text, scale, color, thickness=None, align="left", letter_spacing=LETTER_SPACING):
    """Draw a string onto canvas using the polyline stroke font."""
    if not text:
        return
    t = max(1.0, scale * 0.85) if thickness is None else float(thickness)
    w = text_width(text, scale, t, letter_spacing)

    if align == "center":
        cursor_x = float(x) - w * 0.5 + t * 0.5
    elif align == "right":
        cursor_x = float(x) - w + t * 0.5
    else:
        cursor_x = float(x) + t * 0.5
    origin_y = float(y) + t * 0.5

    for idx, ch in enumerate(text):
        adv, strokes = _lookup_glyph(ch)
        for polyline in strokes:
            if len(polyline) == 1:
                px, py = polyline[0]
                canvas.fill_circle(cursor_x + px * scale, origin_y + py * scale, t * 0.5, color)
            else:
                for i in range(len(polyline) - 1):
                    x0, y0 = polyline[i]
                    x1, y1 = polyline[i + 1]
                    canvas.draw_line(
                        cursor_x + x0 * scale,
                        origin_y + y0 * scale,
                        cursor_x + x1 * scale,
                        origin_y + y1 * scale,
                        color,
                        thickness=t,
                    )
        cursor_x += (adv + letter_spacing) * scale


# =============================================================================
# SECTION 4: PNG ENCODER (PURE STDLIB)
# =============================================================================

def _png_chunk(chunk_type, data):
    """Pack a single PNG chunk with length, type, payload, and IEEE CRC-32."""
    crc = zlib.crc32(chunk_type)
    crc = zlib.crc32(data, crc) & 0xFFFFFFFF
    return struct.pack("!I", len(data)) + chunk_type + data + struct.pack("!I", crc)


def encode_png(canvas, compress_level=9):
    """Encode an RGB Canvas into deterministic PNG bytes."""
    signature = b"\x89PNG\r\n\x1a\n"
    ihdr_data = struct.pack(
        "!IIBBBBB",
        canvas.width,
        canvas.height,
        8,  # bit depth
        2,  # color type: Truecolor RGB
        0,  # compression method: deflate
        0,  # filter method: adaptive
        0,  # interlace method: none
    )

    stride = canvas.width * 3
    raw_rows = bytearray(canvas.height * (stride + 1))
    src = canvas.buf
    dst_pos = 0
    for row in range(canvas.height):
        raw_rows[dst_pos] = 0  # filter type 0 (None)
        dst_pos += 1
        src_start = row * stride
        raw_rows[dst_pos:dst_pos + stride] = src[src_start:src_start + stride]
        dst_pos += stride

    compressed = zlib.compress(bytes(raw_rows), level=compress_level)

    return (
        signature
        + _png_chunk(b"IHDR", ihdr_data)
        + _png_chunk(b"IDAT", compressed)
        + _png_chunk(b"IEND", b"")
    )


def write_png(canvas, filepath):
    """Write Canvas as a PNG file to filepath."""
    png_bytes = encode_png(canvas)
    with open(filepath, "wb") as f:
        f.write(png_bytes)
    return len(png_bytes)


# =============================================================================
# SECTION 5: PAGE LAYOUT SECTIONS
# =============================================================================

def draw_masthead(canvas):
    """Draw top rule, large title, date line in accent red, and double bottom rule."""
    # Top masthead rule
    canvas.fill_rect(CONTENT_X0, MASTHEAD_TOP_Y, CONTENT_W, 4, COLOR_INK)
    canvas.fill_rect(CONTENT_X0, MASTHEAD_TOP_Y + 7, CONTENT_W, 1, COLOR_INK)

    # Main masthead title
    center_x = WIDTH * 0.5
    canvas.draw_text(
        center_x,
        46,
        "THE WORLD IN ONE DAY",
        scale=6.4,
        color=COLOR_INK,
        thickness=5.5,
        align="center",
        letter_spacing=2.0,
    )

    # Date line in accent red flanked by subtle short accent rules
    date_text = "WEDNESDAY 25 NOVEMBER 2026"
    date_scale = 2.4
    date_thick = 2.4
    date_y = 113
    canvas.draw_text(
        center_x,
        date_y,
        date_text,
        scale=date_scale,
        color=COLOR_RED,
        thickness=date_thick,
        align="center",
        letter_spacing=1.95,
    )

    # Double rule line beneath the masthead
    canvas.fill_rect(CONTENT_X0, MASTHEAD_RULE_Y, CONTENT_W, 3, COLOR_INK)
    canvas.fill_rect(CONTENT_X0, MASTHEAD_RULE_Y + 6, CONTENT_W, 1, COLOR_INK)


def get_panel_rects():
    """Return list of (x, y, w, h) tuples for the three top placeholder panels."""
    rects = []
    for idx in range(PANEL_COUNT):
        px = CONTENT_X0 + idx * (PANEL_W + PANEL_GAP)
        rects.append((px, PANEL_Y, PANEL_W, PANEL_H))
    return rects


def _ellipse_points(cx, cy, rx, ry, steps=28):
    """Return polygon vertices approximating an axis-aligned ellipse."""
    pts = []
    for i in range(steps):
        ang = (2.0 * math.pi * i) / steps
        pts.append((cx + rx * math.cos(ang), cy + ry * math.sin(ang)))
    return pts


def _arc_points(cx, cy, rx, ry, start_angle, end_angle, steps=16):
    """Return polyline vertices along an elliptical arc."""
    pts = []
    for i in range(steps + 1):
        t = i / float(steps)
        ang = start_angle + (end_angle - start_angle) * t
        pts.append((cx + rx * math.cos(ang), cy + ry * math.sin(ang)))
    return pts


def _draw_arrowhead(canvas, x0, y0, x1, y1, color, length=14.0, half_width=7.5):
    """Draw a solid triangular arrowhead pointing from (x0, y0) toward tip (x1, y1)."""
    dx = x1 - x0
    dy = y1 - y0
    dist = math.hypot(dx, dy)
    if dist < 1e-6:
        return
    ux = dx / dist
    uy = dy / dist
    px = -uy
    py = ux
    bx = x1 - ux * length
    by = y1 - uy * length
    tri = [
        (x1, y1),
        (bx + px * half_width, by + py * half_width),
        (bx - px * half_width, by - py * half_width),
    ]
    canvas.fill_polygon(tri, color)


def _draw_curved_dashed_arrow(canvas, p0, p1, p2, color, thickness=2.0,
                              dash_len=6.0, gap_len=4.5, head_len=10.0, head_w=5.5):
    """Draw a dashed quadratic Bezier curve from p0 through control p1 to p2 with arrowhead."""
    samples = 48
    pts = []
    for i in range(samples + 1):
        t = i / float(samples)
        u = 1.0 - t
        x = u * u * p0[0] + 2.0 * u * t * p1[0] + t * t * p2[0]
        y = u * u * p0[1] + 2.0 * u * t * p1[1] + t * t * p2[1]
        pts.append((x, y))

    # Measure arc length and walk dashes along the polyline
    cum = [0.0]
    for i in range(1, len(pts)):
        cum.append(cum[-1] + math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]))
    total = cum[-1]
    if total < 1e-6:
        return

    # Stop dashes slightly short of the arrowhead base
    curve_limit = max(0.0, total - head_len * 0.65)

    def sample_at(dist):
        if dist <= 0.0:
            return pts[0]
        if dist >= total:
            return pts[-1]
        for idx in range(1, len(cum)):
            if cum[idx] >= dist:
                seg = cum[idx] - cum[idx - 1]
                frac = 0.0 if seg < 1e-9 else (dist - cum[idx - 1]) / seg
                x = pts[idx - 1][0] + (pts[idx][0] - pts[idx - 1][0]) * frac
                y = pts[idx - 1][1] + (pts[idx][1] - pts[idx - 1][1]) * frac
                return (x, y)
        return pts[-1]

    pos = 0.0
    step = dash_len + gap_len
    while pos < curve_limit:
        end = min(curve_limit, pos + dash_len)
        a = sample_at(pos)
        b = sample_at(end)
        canvas.draw_line(a[0], a[1], b[0], b[1], color, thickness=thickness)
        pos += step

    tail = sample_at(max(0.0, total - head_len))
    _draw_arrowhead(canvas, tail[0], tail[1], p2[0], p2[1], color,
                    length=head_len, half_width=head_w)


def draw_scene_rocket(canvas, sx, sy, sw, sh):
    """Panel 1: Bold rocket liftoff with stars, Tiangong-style space station, and ground."""
    # Sky bands: deep night space at top fading through twilight to horizon haze
    ground_y = sy + sh - 16
    night_h = int(sh * 0.72)
    twilight_h = 18
    canvas.fill_rect(sx, sy, sw, night_h, COLOR_SKY_NIGHT)
    canvas.fill_rect(sx, sy + night_h, sw, twilight_h, COLOR_SKY_TWILIGHT)
    canvas.fill_rect(sx, sy + night_h + twilight_h, sw, ground_y - (sy + night_h + twilight_h), COLOR_SKY_LIGHT)

    # Small white stars in the dark blue sky
    star_dots = (
        (22, 18, 1.5), (46, 36, 1.2), (30, 68, 1.4), (54, 96, 1.1),
        (132, 22, 1.5), (148, 56, 1.2), (160, 96, 1.3),
        (256, 18, 1.4), (268, 72, 1.5), (242, 108, 1.2), (192, 106, 1.1),
    )
    for ox, oy, r in star_dots:
        canvas.fill_circle(sx + ox, sy + oy, r, COLOR_WHITE)

    # Three tiny crisp 4-point cross stars
    for ox, oy, arm in ((18, 44, 4.0), (144, 34, 4.5), (264, 96, 4.0)):
        cx = sx + ox
        cy = sy + oy
        canvas.draw_line(cx - arm, cy, cx + arm, cy, COLOR_WHITE, thickness=1.2)
        canvas.draw_line(cx, cy - arm, cx, cy + arm, COLOR_WHITE, thickness=1.2)

    # Space station (right side): horizontal cylinder + two rectangular solar-panel wings
    st_cx = sx + 214
    st_cy = sy + 52
    # Connecting mast between top and bottom solar wings
    canvas.draw_line(st_cx, st_cy - 34, st_cx, st_cy + 34, COLOR_SILVER, thickness=3.0)

    # Top and bottom rectangular solar-panel wings
    wing_w = 40
    wing_h = 22
    for wy in (st_cy - 34, st_cy + 12):
        wx = st_cx - wing_w // 2
        canvas.fill_rect(wx, wy, wing_w, wing_h, COLOR_SOLAR)
        # Solar cell grid lines
        for gx in range(wx + 8, wx + wing_w, 8):
            canvas.draw_line(gx, wy, gx, wy + wing_h, COLOR_SKY_NIGHT, thickness=1.0)
        canvas.draw_line(wx, wy + wing_h // 2, wx + wing_w, wy + wing_h // 2, COLOR_SKY_NIGHT, thickness=1.0)
        canvas.stroke_rect(wx, wy, wing_w, wing_h, COLOR_WHITE, thickness=1)

    # Horizontal cylindrical station body
    cyl_x = st_cx - 32
    cyl_y = st_cy - 7
    cyl_w = 64
    cyl_h = 14
    # End caps / docking ports
    canvas.fill_rect(cyl_x - 8, st_cy - 4, 9, 8, COLOR_SILVER)
    canvas.stroke_rect(cyl_x - 8, st_cy - 4, 9, 8, COLOR_INK, thickness=1)
    canvas.fill_rect(cyl_x + cyl_w - 1, st_cy - 4, 7, 8, COLOR_SILVER)
    canvas.stroke_rect(cyl_x + cyl_w - 1, st_cy - 4, 7, 8, COLOR_INK, thickness=1)
    # Main cylinder body with bottom shading
    canvas.fill_rect(cyl_x, cyl_y, cyl_w, cyl_h, COLOR_WHITE)
    canvas.fill_rect(cyl_x, cyl_y + 9, cyl_w, 5, COLOR_SILVER)
    canvas.stroke_rect(cyl_x, cyl_y, cyl_w, cyl_h, COLOR_INK, thickness=2)
    # Central hub collar & tiny station windows
    canvas.fill_rect(st_cx - 6, cyl_y - 2, 12, cyl_h + 4, COLOR_SILVER)
    canvas.stroke_rect(st_cx - 6, cyl_y - 2, 12, cyl_h + 4, COLOR_INK, thickness=2)
    canvas.fill_circle(st_cx - 18, st_cy - 1, 2.0, COLOR_SKY_NIGHT)
    canvas.fill_circle(st_cx + 18, st_cy - 1, 2.0, COLOR_SKY_NIGHT)

    # Rocket geometry (left-center)
    rcx = sx + 88
    nose_top_y = sy + 14
    body_top_y = sy + 46
    body_bot_y = sy + 114
    half_w = 15

    # Smoke puffs billowing below and outward along the launchpad
    back_puffs = (
        (rcx - 42, ground_y - 4, 15), (rcx - 24, ground_y - 9, 17),
        (rcx, ground_y - 8, 19), (rcx + 25, ground_y - 10, 18),
        (rcx + 46, ground_y - 5, 16), (rcx + 64, ground_y - 2, 12),
        (rcx - 58, ground_y - 1, 11),
    )
    for cx, cy, rad in back_puffs:
        canvas.fill_circle(cx, cy, rad, COLOR_SMOKE_DARK)

    front_puffs = (
        (rcx - 36, ground_y - 1, 13), (rcx - 18, ground_y - 4, 15),
        (rcx + 2, ground_y - 2, 16), (rcx + 21, ground_y - 5, 15),
        (rcx + 40, ground_y - 1, 13), (rcx + 56, ground_y + 1, 10),
        (rcx - 50, ground_y + 1, 9),
    )
    for cx, cy, rad in front_puffs:
        canvas.fill_circle(cx, cy, rad, COLOR_SMOKE)

    # Bright orange-red flame plume below rocket engine
    outer_flame = [
        (rcx - 11, body_bot_y + 6),
        (rcx - 18, body_bot_y + 24),
        (rcx - 9, body_bot_y + 36),
        (rcx, body_bot_y + 52),
        (rcx + 9, body_bot_y + 36),
        (rcx + 18, body_bot_y + 24),
        (rcx + 11, body_bot_y + 6),
    ]
    mid_flame = [
        (rcx - 8, body_bot_y + 6),
        (rcx - 12, body_bot_y + 22),
        (rcx, body_bot_y + 42),
        (rcx + 12, body_bot_y + 22),
        (rcx + 8, body_bot_y + 6),
    ]
    core_flame = [
        (rcx - 4, body_bot_y + 6),
        (rcx - 5, body_bot_y + 19),
        (rcx, body_bot_y + 31),
        (rcx + 5, body_bot_y + 19),
        (rcx + 4, body_bot_y + 6),
    ]
    canvas.fill_polygon(outer_flame, COLOR_RED)
    canvas.fill_polygon(mid_flame, COLOR_ORANGE)
    canvas.fill_polygon(core_flame, COLOR_YELLOW)

    # Engine nozzle
    nozzle = [
        (rcx - 9, body_bot_y),
        (rcx + 9, body_bot_y),
        (rcx + 12, body_bot_y + 8),
        (rcx - 12, body_bot_y + 8),
    ]
    canvas.fill_polygon(nozzle, COLOR_INK)

    # Two bold side fins
    left_fin = [
        (rcx - half_w, body_bot_y - 28),
        (rcx - half_w - 20, body_bot_y + 4),
        (rcx - half_w - 20, body_bot_y + 10),
        (rcx - half_w, body_bot_y - 2),
    ]
    right_fin = [
        (rcx + half_w, body_bot_y - 28),
        (rcx + half_w + 20, body_bot_y + 4),
        (rcx + half_w + 20, body_bot_y + 10),
        (rcx + half_w, body_bot_y - 2),
    ]
    canvas.fill_polygon(left_fin, COLOR_RED)
    canvas.stroke_polygon(left_fin, COLOR_INK, thickness=2.0)
    canvas.fill_polygon(right_fin, COLOR_RED)
    canvas.stroke_polygon(right_fin, COLOR_INK, thickness=2.0)

    # Tall white rocket body + subtle right shading
    canvas.fill_rect(rcx - half_w, body_top_y, half_w * 2, body_bot_y - body_top_y, COLOR_WHITE)
    canvas.fill_rect(rcx + half_w - 7, body_top_y, 7, body_bot_y - body_top_y, COLOR_SILVER)
    # Red lower stage band
    canvas.fill_rect(rcx - half_w, body_bot_y - 16, half_w * 2, 7, COLOR_RED)
    canvas.stroke_rect(rcx - half_w, body_top_y, half_w * 2, body_bot_y - body_top_y, COLOR_INK, thickness=2)

    # Pointed nose cone with red tip
    nose_poly = [
        (rcx, nose_top_y),
        (rcx + 10, nose_top_y + 15),
        (rcx + half_w, body_top_y),
        (rcx - half_w, body_top_y),
        (rcx - 10, nose_top_y + 15),
    ]
    nose_tip = [
        (rcx, nose_top_y),
        (rcx + 8, nose_top_y + 12),
        (rcx - 8, nose_top_y + 12),
    ]
    canvas.fill_polygon(nose_poly, COLOR_WHITE)
    canvas.fill_polygon(nose_tip, COLOR_RED)
    canvas.stroke_polygon(nose_poly, COLOR_INK, thickness=2.0)

    # Small round rocket window
    win_y = body_top_y + 20
    canvas.fill_circle(rcx, win_y, 9.0, COLOR_SILVER)
    canvas.stroke_circle(rcx, win_y, 9.0, COLOR_INK, thickness=2.0)
    canvas.fill_circle(rcx, win_y, 5.8, COLOR_SOLAR)
    canvas.fill_circle(rcx - 2.0, win_y - 2.0, 1.7, COLOR_WHITE)

    # Ground strip & crisp ground line at bottom of the scene
    canvas.fill_rect(sx, ground_y, sw, sy + sh - ground_y, COLOR_PAPER_BAND)
    canvas.draw_line(sx, ground_y, sx + sw, ground_y, COLOR_INK, thickness=2.2)


def draw_scene_market(canvas, sx, sy, sw, sh):
    """Panel 2: Steeply falling line chart, 3 shrinking bars, and container ship silhouette."""
    # Clean bright newsprint chart backdrop
    canvas.fill_rect(sx, sy, sw, sh, COLOR_WHITE)

    # Chart region (upper 58% of scene)
    ax_x0 = sx + 22
    ax_x1 = sx + sw - 16
    ax_y0 = sy + 14
    ax_y1 = sy + 108

    # Subtle horizontal grid lines
    for gy in (ax_y0 + 18, ax_y0 + 44, ax_y0 + 70):
        canvas.draw_line(ax_x0 + 2, gy, ax_x1, gy, COLOR_GRID, thickness=1.0)
        canvas.draw_line(ax_x0 - 4, gy, ax_x0, gy, COLOR_INK, thickness=1.6)

    # Chart axes
    canvas.draw_line(ax_x0, ax_y0, ax_x0, ax_y1, COLOR_INK, thickness=2.2)
    canvas.draw_line(ax_x0, ax_y1, ax_x1, ax_y1, COLOR_INK, thickness=2.2)

    # Jagged steeply falling stock line (upper left -> lower right)
    chart_pts = [
        (sx + 30, sy + 22),
        (sx + 58, sy + 30),
        (sx + 78, sy + 20),
        (sx + 106, sy + 48),
        (sx + 128, sy + 38),
        (sx + 154, sy + 66),
        (sx + 178, sy + 54),
        (sx + 206, sy + 82),
        (sx + 222, sy + 72),
        (sx + 244, sy + 92),
    ]
    canvas.stroke_polygon(chart_pts, COLOR_RED, thickness=4.2, closed=False)

    # Large red downward arrowhead at end of jagged line
    tip_x = sx + 258
    tip_y = sy + 103
    canvas.draw_line(chart_pts[-1][0], chart_pts[-1][1], tip_x - 6, tip_y - 5, COLOR_RED, thickness=4.2)
    _draw_arrowhead(canvas, chart_pts[-2][0], chart_pts[-2][1], tip_x, tip_y,
                    COLOR_RED, length=21.0, half_width=11.5)

    # Subtle divider shelf above trade/bar area
    bar_base_y = sy + 172

    # Three short vertical bars getting shorter left to right (lower left)
    bars = (
        (sx + 24, 46, COLOR_BLUE),
        (sx + 52, 31, COLOR_BLUE),
        (sx + 80, 17, COLOR_RED),
    )
    bar_w = 20
    for bx, bh, bcol in bars:
        canvas.fill_rect(bx, bar_base_y - bh, bar_w, bh, bcol)
        canvas.stroke_rect(bx, bar_base_y - bh, bar_w, bh, COLOR_INK, thickness=2)
    canvas.draw_line(sx + 18, bar_base_y, sx + 106, bar_base_y, COLOR_INK, thickness=2.0)

    # Container ship silhouette with stacked shipping containers (lower right)
    water_y = sy + 170
    canvas.fill_rect(sx + 114, water_y, sw - 114, sy + sh - water_y, COLOR_WATER)
    canvas.draw_line(sx + 114, water_y, sx + sw, water_y, COLOR_BLUE, thickness=1.5)
    canvas.draw_line(sx + 124, water_y + 7, sx + 176, water_y + 7, COLOR_BLUE, thickness=1.2)
    canvas.draw_line(sx + 204, water_y + 9, sx + 268, water_y + 9, COLOR_BLUE, thickness=1.2)

    # Bridge / superstructure at stern (left side of ship)
    deck_y = sy + 154
    canvas.fill_rect(sx + 132, deck_y - 26, 19, 26, COLOR_PAPER)
    canvas.fill_rect(sx + 135, deck_y - 21, 13, 5, COLOR_INK)
    canvas.stroke_rect(sx + 132, deck_y - 26, 19, 26, COLOR_INK, thickness=2)
    # Funnel & mast on bridge
    canvas.fill_rect(sx + 136, deck_y - 34, 7, 8, COLOR_RED)
    canvas.stroke_rect(sx + 136, deck_y - 34, 7, 8, COLOR_INK, thickness=1)
    canvas.draw_line(sx + 146, deck_y - 26, sx + 146, deck_y - 37, COLOR_INK, thickness=1.6)

    # Stacked shipping containers on deck
    c_w = 21
    c_h = 10
    c_x0 = sx + 155
    row_specs = (
        (deck_y - c_h, (COLOR_RED, COLOR_BLUE, COLOR_SAND_DARK, COLOR_BARREL)),
        (deck_y - c_h * 2, (COLOR_BLUE, COLOR_ORANGE, COLOR_RED, COLOR_BARREL_LIGHT)),
        (deck_y - c_h * 3, (None, COLOR_RED, COLOR_BLUE, None)),
    )
    for ry, cols in row_specs:
        for i, col in enumerate(cols):
            if col is None:
                continue
            cx = c_x0 + i * (c_w + 1)
            canvas.fill_rect(cx, ry, c_w, c_h, col)
            canvas.stroke_rect(cx, ry, c_w, c_h, COLOR_INK, thickness=1)

    # Ship hull silhouette
    hull = [
        (sx + 124, deck_y),
        (sx + 268, deck_y),
        (sx + 256, water_y + 2),
        (sx + 131, water_y + 2),
    ]
    canvas.fill_polygon(hull, COLOR_SHIP_HULL)
    # Red lower waterline accent stripe
    waterline = [
        (sx + 129, water_y - 4),
        (sx + 260, water_y - 4),
        (sx + 256, water_y + 2),
        (sx + 131, water_y + 2),
    ]
    canvas.fill_polygon(waterline, COLOR_RED)
    canvas.stroke_polygon(hull, COLOR_INK, thickness=2.0)


def _draw_barrel(canvas, cx, top_y, width, height, body_col, light_col, dark_col):
    """Draw an upright industrial barrel with elliptical top/bottom and two hoop bands."""
    rx = width * 0.5
    ry_cap = 6.0
    bot_y = top_y + height

    # Bottom ellipse
    bot_pts = _ellipse_points(cx, bot_y, rx, ry_cap, steps=24)
    canvas.fill_polygon(bot_pts, body_col)
    canvas.stroke_polygon(bot_pts, COLOR_INK, thickness=2.0)

    # Cylindrical body with right shadow strip
    x0 = cx - rx
    canvas.fill_rect(x0, top_y, width, height, body_col)
    canvas.fill_rect(cx + rx * 0.35, top_y, rx * 0.65, height, dark_col)
    # Subtle left specular highlight
    canvas.fill_rect(x0 + 4, top_y + 4, 4, height - 8, light_col)

    # Side vertical edges
    canvas.draw_line(x0, top_y, x0, bot_y, COLOR_INK, thickness=2.0)
    canvas.draw_line(cx + rx, top_y, cx + rx, bot_y, COLOR_INK, thickness=2.0)

    # Two horizontal structural band lines curving slightly with the cylinder
    for frac in (0.28, 0.74):
        by = top_y + height * frac
        arc = _arc_points(cx, by, rx, 4.2, 0.0, math.pi, steps=16)
        canvas.stroke_polygon(arc, COLOR_INK, thickness=2.4, closed=False)

    # Curved elliptical top + inner rim
    top_pts = _ellipse_points(cx, top_y, rx, ry_cap, steps=24)
    canvas.fill_polygon(top_pts, light_col)
    canvas.stroke_polygon(top_pts, COLOR_INK, thickness=2.0)
    inner_top = _ellipse_points(cx, top_y, rx * 0.68, ry_cap * 0.55, steps=20)
    canvas.stroke_polygon(inner_top, dark_col, thickness=1.2)


def draw_scene_barrels(canvas, sx, sy, sw, sh):
    """Panel 3: Three upright barrels with warning triangle, sand berm, dust plume, and 100 MI arrow."""
    # Pale dusty sky
    canvas.fill_rect(sx, sy, sw, sh, COLOR_SKY_LIGHT)

    # Grey dust plume rising to the right from behind the berm (overlapping circles)
    plume_back = (
        (sx + 162, sy + 102, 13), (sx + 174, sy + 86, 17),
        (sx + 188, sy + 68, 21), (sx + 208, sy + 54, 23),
        (sx + 226, sy + 44, 17), (sx + 172, sy + 64, 15),
    )
    for cx, cy, r in plume_back:
        canvas.fill_circle(cx, cy, r, COLOR_DUST_DARK)

    plume_mid = (
        (sx + 161, sy + 99, 11), (sx + 173, sy + 83, 15),
        (sx + 186, sy + 65, 18), (sx + 205, sy + 51, 20),
        (sx + 223, sy + 41, 14), (sx + 171, sy + 61, 13),
    )
    for cx, cy, r in plume_mid:
        canvas.fill_circle(cx, cy, r, COLOR_DUST_MID)

    plume_hi = (
        (sx + 170, sy + 78, 9), (sx + 183, sy + 60, 12),
        (sx + 201, sy + 46, 13), (sx + 218, sy + 37, 9),
    )
    for cx, cy, r in plume_hi:
        canvas.fill_circle(cx, cy, r, COLOR_DUST_LIGHT)

    # Curved dashed arrow sweeping away from the dust plume + "100 MI" label
    _draw_curved_dashed_arrow(
        canvas,
        (sx + 210, sy + 40),
        (sx + 240, sy + 16),
        (sx + 272, sy + 26),
        COLOR_RED,
        thickness=2.2,
        dash_len=5.5,
        gap_len=4.0,
        head_len=10.5,
        head_w=5.5,
    )
    canvas.draw_text(
        sx + 246,
        sy + 74,
        "100 MI",
        scale=1.65,
        color=COLOR_RED,
        thickness=1.8,
        align="center",
        letter_spacing=1.85,
    )

    # Low sand berm behind/above the barrels
    berm_ridge = [
        (sx, sy + 114),
        (sx + 38, sy + 100),
        (sx + 98, sy + 94),
        (sx + 162, sy + 98),
        (sx + 224, sy + 109),
        (sx + sw, sy + 114),
    ]
    berm_poly = berm_ridge + [(sx + sw, sy + sh), (sx, sy + sh)]
    canvas.fill_polygon(berm_poly, COLOR_SAND)
    # Foreground ground strip under barrels
    canvas.fill_rect(sx, sy + 164, sw, sy + sh - (sy + 164), COLOR_SAND_DARK)
    canvas.stroke_polygon(berm_ridge, COLOR_INK, thickness=2.0, closed=False)

    # Subtle sand contour dashes on the berm
    for x0, x1, y in ((18, 52, 114), (190, 236, 126), (218, 264, 144), (196, 250, 156)):
        canvas.draw_line(sx + x0, sy + y, sx + x1, sy + y, COLOR_SAND_DARK, thickness=1.5)

    # Three upright barrels (left, right, then middle foreground with warning triangle)
    _draw_barrel(canvas, sx + 44, sy + 94, 42, 72,
                 COLOR_BARREL, COLOR_BARREL_LIGHT, COLOR_BARREL_DARK)
    _draw_barrel(canvas, sx + 150, sy + 94, 42, 72,
                 COLOR_BARREL, COLOR_BARREL_LIGHT, COLOR_BARREL_DARK)
    _draw_barrel(canvas, sx + 97, sy + 88, 50, 82,
                 COLOR_BARREL, COLOR_BARREL_LIGHT, COLOR_BARREL_DARK)

    # Bold warning triangle with exclamation mark on the middle barrel
    tri_cx = sx + 97
    tri_top = sy + 116
    tri_bot = sy + 148
    tri_half = 18.5
    warn_tri = [
        (tri_cx, tri_top),
        (tri_cx + tri_half, tri_bot),
        (tri_cx - tri_half, tri_bot),
    ]
    canvas.fill_polygon(warn_tri, COLOR_YELLOW)
    canvas.stroke_polygon(warn_tri, COLOR_INK, thickness=2.5)
    # Exclamation mark inside warning triangle
    canvas.draw_line(tri_cx, tri_top + 10, tri_cx, tri_top + 22, COLOR_INK, thickness=3.0)
    canvas.fill_circle(tri_cx, tri_top + 27.5, 2.0, COLOR_INK)


PANEL_SPECS = (
    {
        "num": "1",
        "kicker": "SPACE",
        "accent": COLOR_RED,
        "headline": "SHENZHOU-24 LAUNCHES",
        "sub": "FIRST PAKISTANI ASTRONAUT TO TIANGONG STATION",
        "art_fn": draw_scene_rocket,
    },
    {
        "num": "2",
        "kicker": "MARKETS",
        "accent": COLOR_BLUE,
        "headline": "ASIA STOCKS TUMBLE",
        "sub": "US TARIFF PROBE TARGETS 16 TRADING PARTNERS",
        "art_fn": draw_scene_market,
    },
    {
        "num": "3",
        "kicker": "HAZARD",
        "accent": COLOR_INK,
        "headline": "IOWA BLAST SET FOR 9 AM",
        "sub": "9,500 LB OF LEAD AZIDE - EVACUATION ZONE 5 MILES",
        "art_fn": draw_scene_barrels,
    },
)


def draw_panels(canvas):
    """Draw the three top feature panels: header badge, artwork scene, headline, and sub-line."""
    for idx, (px, py, pw, ph) in enumerate(get_panel_rects()):
        spec = PANEL_SPECS[idx]
        accent = spec["accent"]

        # Top header band with accent stripe, numbered badge, and kicker word
        canvas.fill_rect(px + 2, py + 2, pw - 4, PANEL_HEADER_H - 2, COLOR_PAPER_BAND)
        canvas.fill_rect(px + 2, py + 2, pw - 4, 3, accent)
        canvas.fill_rect(px + 2, py + PANEL_HEADER_H, pw - 4, 1, COLOR_INK)

        # Number badge box on left of header band
        badge_x = px + 8
        badge_y = py + 8
        badge_w = 18
        badge_h = 18
        canvas.fill_rect(badge_x, badge_y, badge_w, badge_h, accent)
        canvas.draw_text(
            badge_x + badge_w * 0.5,
            badge_y + 3.0,
            spec["num"],
            scale=1.45,
            color=COLOR_WHITE,
            thickness=1.8,
            align="center",
        )
        # Kicker word beside badge
        canvas.draw_text(
            badge_x + badge_w + 8,
            py + 10.5,
            spec["kicker"],
            scale=1.6,
            color=COLOR_INK,
            thickness=1.8,
            align="left",
            letter_spacing=1.95,
        )

        # Scene box (middle region of panel)
        sx = px + 10
        sy = py + PANEL_HEADER_H + 8
        sw = pw - 20
        sh = 186
        spec["art_fn"](canvas, sx, sy, sw, sh)
        canvas.stroke_rect(sx, sy, sw, sh, COLOR_INK, thickness=1)

        # Lower text region: bold wrapped headline + smaller red wrapped sub-line
        text_x = px + 12
        text_max_w = pw - 24

        hl_scale = 2.95
        hl_thick = 3.3
        hl_spacing = 1.82
        hl_lines = wrap_text(spec["headline"], text_max_w, hl_scale, hl_thick,
                             letter_spacing=hl_spacing)
        hl_y = sy + sh + 11
        hl_step = 29
        for line_i, line in enumerate(hl_lines):
            canvas.draw_text(
                text_x,
                hl_y + line_i * hl_step,
                line,
                scale=hl_scale,
                color=COLOR_INK,
                thickness=hl_thick,
                align="left",
                letter_spacing=hl_spacing,
            )

        sub_scale = 1.55
        sub_thick = 1.65
        sub_spacing = 1.68
        sub_lines = wrap_text(spec["sub"], text_max_w, sub_scale, sub_thick,
                              letter_spacing=sub_spacing)
        sub_y = hl_y + len(hl_lines) * hl_step + 8
        sub_step = 19.5
        for line_i, line in enumerate(sub_lines):
            draw_text(
                canvas,
                text_x,
                sub_y + line_i * sub_step,
                line,
                scale=sub_scale,
                color=COLOR_RED,
                thickness=sub_thick,
                align="left",
                letter_spacing=sub_spacing,
            )

        # Outer box border drawn last so edges stay crisp
        canvas.stroke_rect(px, py, pw, ph, COLOR_INK, thickness=2)


# =============================================================================
# SECTION 5B: LOWER EDITORIAL SECTIONS (BY THE NUMBERS, MORE OF THE DAY, BRIEF)
# =============================================================================

NUMBERS_ITEMS = (
    ("16", "TRADE PARTNERS IN THE US TARIFF PROBE"),
    ("-5.3%", "WORST FALL IN SOUTH KOREAN SHARES ON WEDNESDAY"),
    ("10/12", "COUNTS HUAWEI WAS CONVICTED ON IN NEW YORK"),
    ("5-10", "DAYS THE PAKISTANI ASTRONAUT STAYS IN ORBIT"),
    ("68", "BARRELS OF LEAD AZIDE TO BE DETONATED IN IOWA"),
    ("11", "INJURED IN THE HOUTHI DRONE STRIKE ON RIYADH"),
    ("4.9%", "AUSTRALIA'S ANNUAL INFLATION IN OCTOBER"),
    ("$132.3B", "DELL'S RECORD AI SERVER BACKLOG"),
)

MORE_LEFT_ITEMS = (
    (
        "4. HUAWEI CONVICTED IN US TRIAL",
        "- GUILTY ON 10 OF 12 COUNTS, FROM BANK FRAUD TO STEALING TRADE SECRETS; CLEARED OF RACKETEERING. APPEAL PLANNED.",
    ),
    (
        "5. SENEGAL CHAMPIONS AGAIN",
        "- SPORTS COURT CAS RESTORES SENEGAL'S AFRICA CUP TITLE; THE 1-0 FINAL WIN OVER MOROCCO STANDS.",
    ),
    (
        "6. HOUTHI DRONE HITS RIYADH TOWER",
        "- 11 INJURED IN THE SECOND STRIKE IN A WEEK ON THE PIF TOWER, SAUDI CIVIL DEFENCE SAYS.",
    ),
    (
        "7. ISRAELI STRIKE KILLS HAMAS CHIEF",
        "- SECURITY DIRECTOR NAEEM ABU NAHEL AND SIX OTHERS KILLED IN GAZA CITY, MEDICS SAY.",
    ),
)

MORE_RIGHT_ITEMS = (
    (
        "8. AUSTRALIA INFLATION JUMPS",
        "- PRICES UP 4.9% IN A YEAR, CORE MEASURE 3.8%; CASH RATE ALREADY 4.85% AFTER FIVE HIKES.",
    ),
    (
        "9. JAPAN PRICES AT 36-YEAR HIGH",
        "- SERVICES INFLATION UP 4.2% IN OCTOBER, FUELLING TALK OF A CENTRAL BANK RATE HIKE.",
    ),
    (
        "10. DELL POSTS RECORD QUARTER",
        "- REVENUE $54.94 BILLION AS AI SERVER DEMAND SOARS; FULL-YEAR FORECAST RAISED TO $202 BILLION.",
    ),
    (
        "11. MICROSOFT DECLARES CODE RED",
        "- INTERNAL MEMOS, REPORTED BY REUTERS, FOLLOW THE 24-HOUR OUTAGE THAT HIT OUTLOOK AND TEAMS.",
    ),
)

BRIEF_ITEMS = (
    "CIA AND ODNI HIT BY CYBER BREACH OF UNCLASSIFIED DATA",
    "TRUMP PARDONS THANKSGIVING TURKEYS FREEDOM AND FEATHERS",
    "NEPAL QUAKE OF 5.3 SHAKES KOSHI AND SIKKIM, NO DEATHS REPORTED",
    "US CONSUMER CONFIDENCE AT 103.3, HIGHEST IN NEARLY TWO YEARS",
    "BRENT OIL AT $90.97 AHEAD OF OPEC+ TALKS ON NOV 29",
    "GOLD AT $3,544 AS MARKETS AWAIT US PCE AND GDP DATA",
    "GAZA CIVIL DEFENCE: 85% OF ITS VEHICLES OUT OF SERVICE",
    "RUSSIA'S OWN FIGURES SHOW ALMOST 500,000 WAR DEATHS",
    "UK PANEL TO EXAMINE NUCLEAR TEST VETERANS' HEALTH LEGACY",
    "FOREIGN BUYERS LIFT INDIAN STOCKS AFTER HOLIDAY BREAK",
    "TURKEYS CHASE A WOMAN IN MASSACHUSETTS, BBC'S MOST WATCHED",
)


def draw_section_header(canvas, y, title):
    """Draw a bold ink section title paired with a crisp double editorial rule."""
    scale = 1.85
    thick = 2.2
    spacing = 2.15
    draw_text(
        canvas,
        CONTENT_X0,
        y,
        title,
        scale=scale,
        color=COLOR_INK,
        thickness=thick,
        align="left",
        letter_spacing=spacing,
    )
    title_w = text_width(title, scale, thickness=thick, letter_spacing=spacing)
    rule_x0 = int(round(CONTENT_X0 + title_w + 12))
    rule_w = max(0, CONTENT_X1 - rule_x0)
    if rule_w > 0:
        canvas.fill_rect(rule_x0, y + 5, rule_w, 2, COLOR_INK)
        canvas.fill_rect(rule_x0, y + 9, rule_w, 1, COLOR_INK)


def _word_advance(word, scale, letter_spacing):
    """Return horizontal advance width of word in pixels (excluding trailing spacing)."""
    units = 0.0
    for idx, ch in enumerate(word):
        adv, _ = _lookup_glyph(ch)
        units += adv
        if idx < len(word) - 1:
            units += letter_spacing
    return units * scale


def _wrap_bold_regular(bold_text, regular_text, max_width, scale,
                       bold_thick, reg_thick, bold_spacing, reg_spacing):
    """Word-wrap a bold lead-in followed seamlessly by regular text into styled lines."""
    tokens = [(w, True) for w in bold_text.split()] + [(w, False) for w in regular_text.split()]
    space_adv = (_lookup_glyph(" ")[0] + reg_spacing) * scale

    lines = []
    current = []
    cursor_x = 0.0
    for word, is_bold in tokens:
        sp = bold_spacing if is_bold else reg_spacing
        th = bold_thick if is_bold else reg_thick
        w_adv = _word_advance(word, scale, sp)
        prefix = space_adv if current else 0.0
        if current and cursor_x + prefix + w_adv + th > max_width:
            lines.append(current)
            current = [(word, is_bold)]
            cursor_x = w_adv
        else:
            current.append((word, is_bold))
            cursor_x += prefix + w_adv
    if current:
        lines.append(current)
    return lines


def _draw_styled_line(canvas, x, y, tokens, scale, color,
                      bold_thick, reg_thick, bold_spacing, reg_spacing):
    """Render a single wrapped line containing bold and regular word tokens."""
    space_adv = (_lookup_glyph(" ")[0] + reg_spacing) * scale
    cursor_x = float(x)
    for idx, (word, is_bold) in enumerate(tokens):
        sp = bold_spacing if is_bold else reg_spacing
        th = bold_thick if is_bold else reg_thick
        # Align stroke vertical centers cleanly between bold and regular runs
        y_off = 0.0 if is_bold else (bold_thick - reg_thick) * 0.5
        draw_text(
            canvas,
            cursor_x,
            y + y_off,
            word,
            scale=scale,
            color=color,
            thickness=th,
            align="left",
            letter_spacing=sp,
        )
        cursor_x += _word_advance(word, scale, sp)
        if idx < len(tokens) - 1:
            cursor_x += space_adv


def draw_numbers_section(canvas):
    """Draw Section 1 (BY THE NUMBERS): 4x2 stat grid with red bold values and ink captions."""
    draw_section_header(canvas, NUMBERS_HEADER_Y, "BY THE NUMBERS")

    cols = 4
    rows = 2
    cell_w = CONTENT_W / float(cols)
    grid_y0 = NUMBERS_GRID_Y
    grid_y1 = grid_y0 + NUMBERS_GRID_H

    # Crisp framing rules and internal grid dividers
    canvas.fill_rect(CONTENT_X0, grid_y0, CONTENT_W, 1, COLOR_RULE_LIGHT)
    canvas.fill_rect(CONTENT_X0, grid_y0 + NUMBERS_ROW_H, CONTENT_W, 1, COLOR_RULE_LIGHT)
    canvas.fill_rect(CONTENT_X0, grid_y1, CONTENT_W, 1, COLOR_RULE_LIGHT)
    for col in range(1, cols):
        div_x = int(round(CONTENT_X0 + col * cell_w))
        canvas.fill_rect(div_x, grid_y0 + 4, 1, NUMBERS_GRID_H - 8, COLOR_RULE_LIGHT)

    num_scale = 3.05
    num_thick = 3.45
    num_spacing = 1.85

    cap_scale = 1.2
    cap_thick = 1.05
    cap_spacing = 1.58
    cap_line_step = 12.5

    pad_x = 11
    cap_max_w = cell_w - 2 * pad_x

    for idx, (number_str, caption_str) in enumerate(NUMBERS_ITEMS):
        row = idx // cols
        col = idx % cols
        cx = CONTENT_X0 + col * cell_w + pad_x
        ry = grid_y0 + row * NUMBERS_ROW_H

        draw_text(
            canvas,
            cx,
            ry + 4.0,
            number_str,
            scale=num_scale,
            color=COLOR_RED,
            thickness=num_thick,
            align="left",
            letter_spacing=num_spacing,
        )

        cap_lines = wrap_text(
            caption_str,
            cap_max_w,
            cap_scale,
            thickness=cap_thick,
            letter_spacing=cap_spacing,
        )
        cap_y = ry + 35.0
        for line_i, line in enumerate(cap_lines):
            draw_text(
                canvas,
                cx,
                cap_y + line_i * cap_line_step,
                line,
                scale=cap_scale,
                color=COLOR_INK,
                thickness=cap_thick,
                align="left",
                letter_spacing=cap_spacing,
            )


def draw_more_of_day_section(canvas):
    """Draw Section 2 (MORE OF THE DAY): two columns of numbered stories (4-7 left, 8-11 right)."""
    draw_section_header(canvas, MORE_HEADER_Y, "MORE OF THE DAY")

    scale = 1.24
    bold_thick = 1.58
    reg_thick = 1.04
    bold_spacing = 1.92
    reg_spacing = 1.56
    line_step = 13.6
    item_gap = 5.2

    columns = (
        (CONTENT_X0, MORE_LEFT_ITEMS),
        (CONTENT_X0 + TWO_COL_W + TWO_COL_GAP, MORE_RIGHT_ITEMS),
    )

    max_bottom = MORE_BODY_Y
    for col_x, items in columns:
        cur_y = float(MORE_BODY_Y)
        for item_i, (headline, detail) in enumerate(items):
            lines = _wrap_bold_regular(
                headline,
                detail,
                TWO_COL_W,
                scale,
                bold_thick,
                reg_thick,
                bold_spacing,
                reg_spacing,
            )
            for line_tokens in lines:
                _draw_styled_line(
                    canvas,
                    col_x,
                    cur_y,
                    line_tokens,
                    scale,
                    COLOR_INK,
                    bold_thick,
                    reg_thick,
                    bold_spacing,
                    reg_spacing,
                )
                cur_y += line_step
            if item_i < len(items) - 1:
                cur_y += item_gap
        col_bottom = cur_y - line_step + text_height(scale, bold_thick)
        if col_bottom > max_bottom:
            max_bottom = col_bottom

    div_h = max(0, int(round(max_bottom - MORE_BODY_Y)))
    canvas.fill_rect(TWO_COL_DIV_X, MORE_BODY_Y, 1, div_h, COLOR_RULE_LIGHT)


def draw_headlines_in_brief_section(canvas):
    """Draw Section 3 (HEADLINES IN BRIEF): two columns of short red-bulleted briefs."""
    draw_section_header(canvas, BRIEF_HEADER_Y, "HEADLINES IN BRIEF")

    scale = 1.22
    thick = 1.05
    spacing = 1.58
    line_step = 12.1
    item_gap = 2.5

    bullet_size = 5
    bullet_indent = 11
    text_max_w = TWO_COL_W - bullet_indent

    left_items = BRIEF_ITEMS[:6]
    right_items = BRIEF_ITEMS[6:]
    columns = (
        (CONTENT_X0, left_items),
        (CONTENT_X0 + TWO_COL_W + TWO_COL_GAP, right_items),
    )

    line_h = text_height(scale, thick)
    max_bottom = BRIEF_BODY_Y
    for col_x, items in columns:
        cur_y = float(BRIEF_BODY_Y)
        for item_i, text in enumerate(items):
            lines = wrap_text(
                text,
                text_max_w,
                scale,
                thickness=thick,
                letter_spacing=spacing,
            )
            bullet_y = int(round(cur_y + (line_h - bullet_size) * 0.5))
            canvas.fill_rect(col_x, bullet_y, bullet_size, bullet_size, COLOR_RED)
            for line in lines:
                draw_text(
                    canvas,
                    col_x + bullet_indent,
                    cur_y,
                    line,
                    scale=scale,
                    color=COLOR_INK,
                    thickness=thick,
                    align="left",
                    letter_spacing=spacing,
                )
                cur_y += line_step
            if item_i < len(items) - 1:
                cur_y += item_gap
        col_bottom = cur_y - line_step + line_h
        if col_bottom > max_bottom:
            max_bottom = col_bottom

    div_h = max(0, int(round(max_bottom - BRIEF_BODY_Y)))
    canvas.fill_rect(TWO_COL_DIV_X, BRIEF_BODY_Y, 1, div_h, COLOR_RULE_LIGHT)


def draw_footer(canvas):
    """Draw bottom footer rule and centered source attribution line."""
    canvas.fill_rect(CONTENT_X0, FOOTER_RULE_Y, CONTENT_W, 2, COLOR_INK)
    canvas.draw_text(
        WIDTH * 0.5,
        FOOTER_TEXT_Y,
        "ONE DAY - ONE PAGE - SOURCES: WIRE REPORTS OF 25 NOV 2026",
        scale=1.65,
        color=COLOR_INK_MUTED,
        thickness=1.6,
        align="center",
        letter_spacing=1.80,
    )


# =============================================================================
# SECTION 6: MAIN ENTRY POINT
# =============================================================================

def render_page():
    """Compose the full 1024x1024 infographic page and return the Canvas."""
    canvas = Canvas(WIDTH, HEIGHT, bg_color=COLOR_PAPER, ss=SUPERSAMPLE)
    draw_masthead(canvas)
    draw_panels(canvas)
    draw_numbers_section(canvas)
    draw_more_of_day_section(canvas)
    draw_headlines_in_brief_section(canvas)
    draw_footer(canvas)
    return canvas.downsample()


def main():
    out_dir = os.environ.get("MAKEFUN_OUTPUT_DIR", "out") or "out"
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "entry.png")
    canvas = render_page()
    byte_size = write_png(canvas, out_path)
    print(f"Wrote {out_path} ({byte_size} bytes)")


if __name__ == "__main__":
    main()
