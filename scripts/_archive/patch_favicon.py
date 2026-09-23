from pathlib import Path

# 1x1 PNG favicon
import struct
import zlib

def png_1x1(rgb=(166, 124, 0)):
    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    ihdr = chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
    raw = b"\x00" + bytes(rgb)
    idat = chunk(b"IDAT", zlib.compress(raw))
    return b"\x89PNG\r\n\x1a\n" + ihdr + idat + chunk(b"IEND", b"")

Path("favicon.ico").write_bytes(png_1x1())

# main.py 提供 favicon
p = Path("app/main.py")
t = p.read_text(encoding="utf-8")
if "favicon.ico" not in t:
    t = t.replace(
        '@app.get("/health")',
        '''@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> FileResponse:
    return FileResponse(BASE_DIR / "favicon.ico", media_type="image/x-icon")


@app.get("/health")''',
        1,
    )
    p.write_text(t, encoding="utf-8")
    print("favicon route")
print("ok")
