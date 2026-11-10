# build_windows.py — for the kit's maintainer only (not in the ZIPs).
# Builds the no-Python Windows program into מערכת/bin-win with PyInstaller (onedir: MoodleSorter.exe for the launchers,
# MoodleSorterBg.exe without a window for the background sorter). Task Manager shows them as "סדר מהמודל". Run it with a Python that has PyInstaller, preferably from
# a venv outside iCloud:   <venv>\Scripts\python בנייה\build_windows.py  <work folder outside iCloud>
import re, shutil, struct, subprocess, sys, zlib
from pathlib import Path

TOP = Path(__file__).resolve().parent.parent
KIT = TOP / "מערכת"
WORK = Path(sys.argv[1]).resolve()
VERSION = re.search(r'VERSION = "([\d.]+)"', (KIT / "sort_downloads.py").read_text(encoding="utf-8")).group(1)
nums = (list(map(int, VERSION.split("."))) + [0, 0, 0, 0])[:4]


def icon(path):
    """A small icon (blue square, white arrow down into a tray), drawn in code: 16, 32 and 48 px PNGs inside an .ico."""
    def png(n):
        rows = []
        for y in range(n):
            row = bytearray([0])
            for x in range(n):
                u, v = (x + .5) / n, (y + .5) / n
                r = .18                                               # rounded corners
                cx, cy = min(max(u, r), 1 - r), min(max(v, r), 1 - r)
                inside = (u - cx) ** 2 + (v - cy) ** 2 <= r * r
                white = (.43 <= u <= .57 and .18 <= v <= .52) or (v >= .45 and v <= .66 and abs(u - .5) <= (.66 - v) * 1.1) \
                    or (.22 <= u <= .78 and .74 <= v <= .82) or ((.22 <= u <= .29 or .71 <= u <= .78) and .62 <= v <= .82)
                row += bytes((255, 255, 255, 255) if inside and white else (11, 79, 138, 255) if inside else (0, 0, 0, 0))
            rows.append(bytes(row))
        raw = zlib.compress(b"".join(rows), 9)
        chunk = lambda t, d: struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d))
        return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", n, n, 8, 6, 0, 0, 0)) + chunk(b"IDAT", raw) + chunk(b"IEND", b"")
    imgs = [png(n) for n in (16, 32, 48)]
    head = struct.pack("<HHH", 0, 1, len(imgs)); off = 6 + 16 * len(imgs); dirs = b""
    for n, b in zip((16, 32, 48), imgs):
        dirs += struct.pack("<BBBBHHII", n, n, 0, 0, 1, 32, len(b), off); off += len(b)
    path.write_bytes(head + dirs + b"".join(imgs))


shutil.rmtree(WORK, ignore_errors=True); WORK.mkdir(parents=True)
shutil.copy2(KIT / "sort_downloads.py", WORK / "sort_downloads.py")
icon(WORK / "MoodleSorter.ico")
def version_file(name, exe, description):
    (WORK / name).write_text(f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={tuple(nums)}, prodvers={tuple(nums)}, mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[StringFileInfo([StringTable('040904B0', [
    StringStruct('CompanyName', 'סדר מהמודל (קוד פתוח)'),
    StringStruct('FileDescription', '{description}'),
    StringStruct('FileVersion', '{VERSION}'), StringStruct('InternalName', 'MoodleSorter'),
    StringStruct('LegalCopyright', 'Free to use and share'), StringStruct('OriginalFilename', '{exe}'),
    StringStruct('ProductName', 'סדר מהמודל'), StringStruct('ProductVersion', '{VERSION}')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])])
""", encoding="utf-8")


version_file("version_cli.txt", "MoodleSorter.exe", "סדר מהמודל")
version_file("version_bg.txt", "MoodleSorterBg.exe", "סדר מהמודל (ברקע)")
(WORK / "MoodleSorter.spec").write_text("""
a = Analysis(['sort_downloads.py'], excludes=['tkinter', 'unittest', 'pydoc', 'doctest', 'test', 'pdb', 'xmlrpc', 'sqlite3', 'decimal', '_decimal', 'lzma', '_lzma', 'bz2', '_bz2', '_zstd', 'compression.zstd'])   # (v6.5: ssl/socket/http/email stay: the self-update downloads over HTTPS)
pyz = PYZ(a.pure)
common = dict(exclude_binaries=True, icon='MoodleSorter.ico', upx=False, strip=False)
cli = EXE(pyz, a.scripts, [], name='MoodleSorter', console=True, version='version_cli.txt', **common)
bg = EXE(pyz, a.scripts, [], name='MoodleSorterBg', console=False, version='version_bg.txt', **common)
COLLECT(cli, bg, a.binaries, a.datas, upx=False, strip=False, name='bin-win')
""", encoding="utf-8")
subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--log-level", "WARN", "MoodleSorter.spec"], cwd=WORK, check=True)
out = WORK / "dist" / "bin-win"
r = subprocess.run([str(out / "MoodleSorter.exe"), "--version"], capture_output=True, text=True)
assert r.returncode == 0 and VERSION in r.stdout, (r.returncode, r.stdout, r.stderr)
shutil.rmtree(KIT / "bin-win", ignore_errors=True)
shutil.copytree(out, KIT / "bin-win")
(KIT / "bin-win" / "version.txt").write_text(VERSION, encoding="utf-8")   # _build_release.py puts it in the update only if it matches
size = sum(f.stat().st_size for f in (KIT / "bin-win").rglob("*") if f.is_file())
print(f"built bin-win v{VERSION}: {sum(1 for f in (KIT / 'bin-win').rglob('*') if f.is_file())} files, {size / 1e6:.1f} MB; {r.stdout.strip()}")
