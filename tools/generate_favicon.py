#!/usr/bin/env python3
"""Generate gradient MD favicon assets without external dependencies."""
import math
import struct
import zlib
from pathlib import Path

# Palette & layout pulled from site theme (nav badge gradient + 14px radius on 44px square)
START_COLOR = (108, 92, 231)
END_COLOR = (0, 245, 212)
CORNER_RADIUS = 14 / 44

# Letter geometry in normalized 0..1 coordinates
M_TOP = 0.22
M_BOTTOM = 0.78
M_PATH = [
    (0.28, M_BOTTOM),
    (0.28, M_TOP),
    (0.37, 0.40),
    (0.46, M_TOP),
    (0.46, M_BOTTOM),
]
M_STROKE = 0.14

D_TOP = M_TOP
D_BOTTOM = M_BOTTOM
D_STEM_X = M_PATH[-1][0]
D_STEM_WIDTH = M_STROKE
D_STROKE = M_STROKE
D_CENTER_X = D_STEM_X + D_STEM_WIDTH / 2 + (D_BOTTOM - D_TOP) / 2 + D_STROKE / 2
D_CENTER_Y = (D_TOP + D_BOTTOM) / 2
D_OUTER_RADIUS = (D_BOTTOM - D_TOP) / 2 + D_STROKE / 2
D_INNER_RADIUS = D_OUTER_RADIUS - D_STROKE

NOTCH_TRIANGLE = [
    (0.82, 0.27),
    (0.98, 0.20),
    (0.98, 0.34),
]

AA_GRID_SIZE = 3
AA_OFFSETS = [
    ((i + 0.5) / AA_GRID_SIZE, (j + 0.5) / AA_GRID_SIZE)
    for j in range(AA_GRID_SIZE)
    for i in range(AA_GRID_SIZE)
]


def clamp(value, low, high):
    return max(low, min(high, value))


def lerp(a, b, t):
    return a + (b - a) * t


def gradient_color(u, v):
    t = clamp(0.65 * u + 0.35 * v, 0.0, 1.0)
    r = int(round(lerp(START_COLOR[0], END_COLOR[0], t)))
    g = int(round(lerp(START_COLOR[1], END_COLOR[1], t)))
    b = int(round(lerp(START_COLOR[2], END_COLOR[2], t)))
    return r, g, b


def point_distance_to_segment(px, py, ax, ay, bx, by):
    abx = bx - ax
    aby = by - ay
    l2 = abx * abx + aby * aby
    if l2 == 0:
        return math.hypot(px - ax, py - ay)
    t = ((px - ax) * abx + (py - ay) * aby) / l2
    t = clamp(t, 0.0, 1.0)
    proj_x = ax + t * abx
    proj_y = ay + t * aby
    return math.hypot(px - proj_x, py - proj_y)


def polyline_distance(px, py, points):
    return min(
        point_distance_to_segment(px, py, x1, y1, x2, y2)
        for (x1, y1), (x2, y2) in zip(points, points[1:])
    )


def inside_triangle(px, py, tri):
    (x1, y1), (x2, y2), (x3, y3) = tri
    denom = (y2 - y3) * (x1 - x3) + (x3 - x2) * (y1 - y3)
    if denom == 0:
        return False
    a = ((y2 - y3) * (px - x3) + (x3 - x2) * (py - y3)) / denom
    b = ((y3 - y1) * (px - x3) + (x1 - x3) * (py - y3)) / denom
    c = 1 - a - b
    return 0 <= a <= 1 and 0 <= b <= 1 and 0 <= c <= 1


def rounded_mask(u, v):
    r = CORNER_RADIUS
    half = 0.5
    core = 0.5 - r
    dx = max(abs(u - half) - core, 0.0)
    dy = max(abs(v - half) - core, 0.0)
    if dx * dx + dy * dy <= r * r:
        return 1
    return 0


def inside_m(u, v):
    if v < M_TOP - M_STROKE or v > M_BOTTOM + M_STROKE:
        return False
    dist = polyline_distance(u, v, M_PATH)
    return dist <= M_STROKE / 2


def inside_d(u, v):
    in_stem = (
        D_TOP <= v <= D_BOTTOM
        and abs(u - D_STEM_X) <= D_STEM_WIDTH / 2
    )
    dx = u - D_CENTER_X
    dy = v - D_CENTER_Y
    dist = math.hypot(dx, dy)
    in_arc = (
        u >= D_STEM_X
        and D_INNER_RADIUS <= dist <= D_OUTER_RADIUS
    )
    return in_stem or in_arc


def letter_mask(u, v):
    if inside_triangle(u, v, NOTCH_TRIANGLE):
        return 0
    return 1 if (inside_m(u, v) or inside_d(u, v)) else 0


def compose_pixel(bg_rgb, bg_alpha, fg_rgb, fg_alpha):
    if fg_alpha <= 0:
        return bg_rgb, bg_alpha
    if bg_alpha <= 0:
        return fg_rgb, fg_alpha
    out_alpha = fg_alpha + bg_alpha * (1 - fg_alpha)
    if out_alpha == 0:
        return (0, 0, 0), 0
    r = (fg_rgb[0] * fg_alpha + bg_rgb[0] * bg_alpha * (1 - fg_alpha)) / out_alpha
    g = (fg_rgb[1] * fg_alpha + bg_rgb[1] * bg_alpha * (1 - fg_alpha)) / out_alpha
    b = (fg_rgb[2] * fg_alpha + bg_rgb[2] * bg_alpha * (1 - fg_alpha)) / out_alpha
    return (int(round(r)), int(round(g)), int(round(b))), out_alpha


def generate_icon(size):
    pixels = bytearray(size * size * 4)
    samples = len(AA_OFFSETS)
    for y in range(size):
        for x in range(size):
            u_center = (x + 0.5) / size
            v_center = (y + 0.5) / size
            bg_rgb = gradient_color(u_center, v_center)

            bg_acc = 0.0
            letter_acc = 0.0
            for ox, oy in AA_OFFSETS:
                u = (x + ox) / size
                v = (y + oy) / size
                bg = rounded_mask(u, v)
                bg_acc += bg
                if bg:
                    letter_acc += letter_mask(u, v)

            bg_alpha = bg_acc / samples
            letter_alpha = letter_acc / samples

            index = (y * size + x) * 4
            if bg_alpha <= 0.0:
                pixels[index:index + 4] = b"\x00\x00\x00\x00"
                continue

            rgb, alpha = compose_pixel(bg_rgb, bg_alpha, (255, 255, 255), letter_alpha)
            a = int(round(alpha * 255))
            pixels[index:index + 4] = bytes((rgb[0], rgb[1], rgb[2], a))
    return pixels


def write_png(path, size, pixels):
    width = height = size
    raw = bytearray()
    stride = width * 4
    for y in range(height):
        raw.append(0)
        start = y * stride
        raw.extend(pixels[start:start + stride])
    compressed = zlib.compress(bytes(raw), level=9)

    def chunk(tag, data):
        length = struct.pack('!I', len(data))
        crc = struct.pack('!I', zlib.crc32(tag + data) & 0xFFFFFFFF)
        return length + tag + data + crc

    ihdr = struct.pack('!IIBBBBB', width, height, 8, 6, 0, 0, 0)

    with open(path, 'wb') as f:
        f.write(b"\x89PNG\r\n\x1a\n")
        f.write(chunk(b'IHDR', ihdr))
        f.write(chunk(b'IDAT', compressed))
        f.write(chunk(b'IEND', b''))


def write_ico(path, sizes, pixel_maps):
    entries = []
    images_data = []
    offset = 6 + 16 * len(sizes)

    for size, pixels in zip(sizes, pixel_maps):
        width = height = size
        row_stride = width * 4
        xor_bytes = bytearray()
        for y in range(height - 1, -1, -1):
            start = y * row_stride
            row = pixels[start:start + row_stride]
            for x in range(0, len(row), 4):
                r, g, b, a = row[x:x + 4]
                xor_bytes.extend((b, g, r, a))
        and_row_bytes = ((width + 31) // 32) * 4
        and_mask = bytearray(and_row_bytes * height)
        for y in range(height):
            for x in range(width):
                idx = (height - 1 - y) * row_stride + x * 4 + 3
                alpha = pixels[idx]
                if alpha < 128:
                    byte_index = y * and_row_bytes + x // 8
                    bit = 7 - (x % 8)
                    and_mask[byte_index] |= (1 << bit)
        header = struct.pack(
            '<IIIHHIIIIII',
            40,
            width,
            height * 2,
            1,
            32,
            0,
            len(xor_bytes) + len(and_mask),
            0,
            0,
            0,
            0,
        )
        image_data = header + xor_bytes + and_mask
        images_data.append(image_data)
        entry = struct.pack(
            '<BBBBHHII',
            size if size < 256 else 0,
            size if size < 256 else 0,
            0,
            0,
            1,
            32,
            len(image_data),
            offset,
        )
        entries.append(entry)
        offset += len(image_data)

    with open(path, 'wb') as f:
        f.write(struct.pack('<HHH', 0, 1, len(sizes)))
        for entry in entries:
            f.write(entry)
        for data in images_data:
            f.write(data)


def main():
    output_dir = Path('.')
    primary_size = 512
    primary_pixels = generate_icon(primary_size)
    write_png(output_dir / 'favicon.png', primary_size, primary_pixels)

    ico_sizes = [256, 128, 64, 32, 16]
    pixel_sets = [generate_icon(size) for size in ico_sizes]
    write_ico(output_dir / 'favicon.ico', ico_sizes, pixel_sets)


if __name__ == '__main__':
    main()
