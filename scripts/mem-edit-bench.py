#!/usr/bin/env python3
"""Measure tinymist RSS growth vs. number of edits.

Spawns `tinymist lsp`, opens FILE, applies N typing-like incremental edits
(insert a char, then delete it again) and samples VmRSS every K edits.
Prints CSV (edits,rss_kb) and the least-squares slope over the second half.

--truncate-to-bytes rewrites FILE in place: pass a COPY of your project as --root.
"""
import argparse, json, os, queue, random, struct, subprocess, sys, threading, time
from pathlib import Path


def rss_kb(pid):
    for line in Path(f"/proc/{pid}/status").read_text().splitlines():
        if line.startswith("VmRSS:"):
            return int(line.split()[1])


def slope(pts):
    n = len(pts)
    mx = sum(x for x, _ in pts) / n
    my = sum(y for _, y in pts) / n
    den = sum((x - mx) ** 2 for x, _ in pts)
    return sum((x - mx) * (y - my) for x, y in pts) / den if den else 0.0


def census(pid, probes):
    """Count resident anonymous-heap copies of each probe (swapped-out pages are skipped)."""
    page, counts = 4096, [0] * len(probes)
    with open(f"/proc/{pid}/mem", "rb", 0) as mem, open(f"/proc/{pid}/pagemap", "rb", 0) as pm:
        for ln in open(f"/proc/{pid}/maps"):
            f = ln.split()
            if (len(f) > 5 and f[5] != "[heap]") or "r" not in f[1] or f[1][3] == "s":
                continue
            a, b = (int(x, 16) for x in f[0].split("-"))
            pm.seek(a // page * 8)
            ents = struct.unpack(f"<{(b - a) // page}Q", pm.read((b - a) // page * 8))
            i = 0
            while i < len(ents):
                j, here = i, ents[i] >> 63
                while j < len(ents) and ents[j] >> 63 == here:
                    j += 1
                for off in range(i, j, 16384) if here else ():
                    mem.seek(a + off * page)
                    try:
                        buf = mem.read((min(j, off + 16384) - off) * page)
                    except OSError:
                        break
                    counts = [c + buf.count(q) for c, q in zip(counts, probes)]
                i = j
    return max(counts)


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--root", required=True)
    a.add_argument("--file", default="main.typ", help="entry file relative to root")
    a.add_argument("--edits", type=int, default=2000)
    a.add_argument("--sample-every", type=int, default=100)
    a.add_argument("--binary", default="target/release/tinymist")
    a.add_argument("--truncate-to-bytes", type=int)
    a.add_argument("--wait", type=float, default=2.0, help="max seconds to wait for diagnostics per edit")
    a.add_argument("--seed", type=int, default=1)
    a.add_argument("--requests", default="", help="comma list sent after each edit, like an editor: tokens,color,symbol,highlight,completion")
    a.add_argument("--census", action="store_true", help="also count document-text copies in the server heap (reads /proc/<pid>/mem)")
    args = a.parse_args()

    root = Path(args.root).resolve()
    path = root / args.file
    text = path.read_bytes()
    if args.truncate_to_bytes:
        text = text[: args.truncate_to_bytes]
        path.write_bytes(text)
    text = text.decode("utf-8", errors="ignore")
    uri = path.as_uri()

    p = subprocess.Popen([args.binary, "lsp"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                         stderr=subprocess.DEVNULL)
    diag = queue.Queue()
    last_rid = {}
    lock = threading.Lock()

    def send(msg):
        body = json.dumps(msg).encode()
        with lock:
            p.stdin.write(b"Content-Length: %d\r\n\r\n" % len(body) + body)
            p.stdin.flush()

    def reader():
        while True:
            n = 0
            while True:
                h = p.stdout.readline()
                if not h:
                    return
                if h.strip() == b"":
                    break
                if h.lower().startswith(b"content-length:"):
                    n = int(h.split(b":")[1])
            m = json.loads(p.stdout.read(n))
            if "method" in m and "id" in m:  # server request: reply with a benign result
                res = [None] * len(m.get("params", {}).get("items", [])) if m["method"] == "workspace/configuration" else None
                send({"jsonrpc": "2.0", "id": m["id"], "result": res})
            elif isinstance(m.get("result"), dict) and "resultId" in m["result"]:
                last_rid["id"] = m["result"]["resultId"]
            elif m.get("method") == "textDocument/publishDiagnostics":
                diag.put(1)

    threading.Thread(target=reader, daemon=True).start()

    def req(id, method, params):
        send({"jsonrpc": "2.0", "id": id, "method": method, "params": params})

    def note(method, params):
        send({"jsonrpc": "2.0", "method": method, "params": params})

    req(1, "initialize", {"processId": os.getpid(), "rootUri": root.as_uri(),
                          "workspaceFolders": [{"uri": root.as_uri(), "name": "w"}],
                          "capabilities": {"workspace": {"configuration": True}}})
    note("initialized", {})
    note("textDocument/didOpen", {"textDocument": {"uri": uri, "languageId": "typst", "version": 1, "text": text}})

    def wait_diag(t):
        try:
            diag.get(timeout=t)
        except queue.Empty:
            pass

    wait_diag(60)  # warmup: first compile
    rng = random.Random(args.seed)
    ver, pending, pts, rid, lat = 1, None, [], [1], []

    def pos(off):
        pre = text[:off]
        line = pre.count("\n")
        return {"line": line, "character": len(pre[pre.rfind("\n") + 1:].encode("utf-16-le")) // 2}

    raw = text.encode()
    lines = [l for l in raw.split(b"\n") if len(l) > 60]
    probes = ([lines[len(lines) * k // 4][:60] for k in (1, 2, 3)] if lines
              else [raw[len(raw) * k // 4:][:40] for k in (1, 2, 3)])
    print("edits,rss_kb" + (",doc_copies" if args.census else ""))
    for i in range(args.edits + 1):
        if i % args.sample_every == 0:
            r = rss_kb(p.pid)
            pts.append((i, r))
            print(f"{i},{r}" + (f",{census(p.pid, probes)}" if args.census else ""), flush=True)
        if i == args.edits:
            break
        if pending is None:  # insert one char
            off = rng.randrange(len(text) + 1)
            ch = rng.choice("abcxyz ")
            rng_ = {"start": pos(off), "end": pos(off)}
            change = {"range": rng_, "text": ch}
            text = text[:off] + ch + text[off:]
            pending = off
        else:  # delete it again
            rng_ = {"start": pos(pending), "end": pos(pending + 1)}
            change = {"range": rng_, "text": ""}
            text = text[:pending] + text[pending + 1:]
            pending = None
        ver += 1
        note("textDocument/didChange", {"textDocument": {"uri": uri, "version": ver}, "contentChanges": [change]})
        t0 = time.monotonic()
        wait_diag(args.wait)
        # an edit that leaves the diagnostics unchanged publishes nothing and waits the full --wait
        lat.append(time.monotonic() - t0)
        td, at = {"uri": uri}, pos(min(max(pending if pending is not None else off, 0), len(text)))
        for r in filter(None, args.requests.split(",")):
            rid[0] += 1
            if r == "tokens":
                if "id" in last_rid:
                    req(rid[0], "textDocument/semanticTokens/full/delta", {"textDocument": td, "previousResultId": last_rid["id"]})
                else:
                    req(rid[0], "textDocument/semanticTokens/full", {"textDocument": td})
            elif r == "color":
                req(rid[0], "textDocument/documentColor", {"textDocument": td})
            elif r == "symbol":
                req(rid[0], "textDocument/documentSymbol", {"textDocument": td})
            elif r == "highlight":
                req(rid[0], "textDocument/documentHighlight", {"textDocument": td, "position": at})
            elif r == "completion":
                req(rid[0], "textDocument/completion", {"textDocument": td, "position": at})

    half = [pt for pt in pts if pt[0] >= args.edits / 2]
    print(f"# doc_bytes={len(text.encode())} slope_second_half_kb_per_edit={slope(half):.4f}")
    lat.sort()
    print(f"# diag_wait_ms mean={sum(lat) / len(lat) * 1000:.0f} p95={lat[int(len(lat) * 0.95)] * 1000:.0f} max={lat[-1] * 1000:.0f}")
    hwm = next(l for l in Path(f"/proc/{p.pid}/status").read_text().splitlines() if l.startswith("VmHWM:"))
    print(f"# peak_{hwm.split()[0].lower()}_kb={hwm.split()[1]}")
    p.kill()


if __name__ == "__main__":
    sys.exit(main())
