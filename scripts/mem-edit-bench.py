#!/usr/bin/env python3
"""Measure tinymist RSS growth vs. number of edits.

Spawns `tinymist lsp`, opens FILE, applies N typing-like incremental edits
(insert a char, then delete it again) and samples VmRSS every K edits.
Prints CSV (edits,rss_kb) and the least-squares slope over the second half.

--truncate-to-bytes rewrites FILE in place: pass a COPY of your project as --root.
"""
import argparse, json, os, queue, random, subprocess, sys, threading
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
    ver, pending, pts = 1, None, []

    def pos(off):
        pre = text[:off]
        line = pre.count("\n")
        return {"line": line, "character": len(pre[pre.rfind("\n") + 1:].encode("utf-16-le")) // 2}

    print("edits,rss_kb")
    for i in range(args.edits + 1):
        if i % args.sample_every == 0:
            r = rss_kb(p.pid)
            pts.append((i, r))
            print(f"{i},{r}", flush=True)
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
        wait_diag(args.wait)

    half = [pt for pt in pts if pt[0] >= args.edits / 2]
    print(f"# doc_bytes={len(text.encode())} slope_second_half_kb_per_edit={slope(half):.4f}")
    hwm = next(l for l in Path(f"/proc/{p.pid}/status").read_text().splitlines() if l.startswith("VmHWM:"))
    print(f"# peak_{hwm.split()[0].lower()}_kb={hwm.split()[1]}")
    p.kill()


if __name__ == "__main__":
    sys.exit(main())
