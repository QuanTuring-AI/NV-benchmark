#!/usr/bin/env python3
"""Vol.4 · a server that answers at once, to find the load tool's own ceiling.

It holds no model and uses no card. Every POST is read to its end and answered immediately with one prepared body of
the size a retrieval NIM returns for that request shape. What a load tool reaches against it is what the tool itself
can send, receive and record per second when the server costs (almost) nothing: a rate a NIM measured with the same
tool can be set against. If a NIM's rate is far below it, the tool was not what held the NIM's rate down.

  shape          answer                                     served on
  query          an embeddings answer with 1 vector         /v1/embeddings   and /shape/query
  passage        an embeddings answer with 64 vectors       /v1/embeddings   and /shape/passage
  passages_100   a ranking answer with 100 entries          /v1/ranking      and /shape/passages_100
  passages_10    a ranking answer with 10 entries           /v1/ranking      and /shape/passages_10
  GET /v1/health/ready                                      a small ready answer
One server holds at most one embeddings shape and one ranking shape, so that the NIM's own two paths are unambiguous
and the request does not have to be parsed to choose the answer.
The size of each body in bytes is given on the command line (the sizes a real NIM's answers had, as the load tool
recorded them); the numbers inside are made up by a fixed rule and mean nothing. Headers and body go out in one write.

What it can and cannot show: an upper end for the tool on this host, with this request and answer size. It is one
asyncio thread of Python: at very high rates it may be this server, not the tool, that is the limit, so the figure is
"the tool reaches at least this". It does not occupy the host's CPU the way a real NIM does while the tool runs.

usage: instant_answer_server.py --bytes query=N,passages_100=N [--port 8000]      (one embeddings shape, one ranking shape, or one of them)
"""
import argparse, asyncio, json, random, sys

SHAPES = {"query": ("embedding", 1), "passage": ("embedding", 64), "passages_100": ("ranking", 100), "passages_10": ("ranking", 10)}
NIM_PATH = {"embedding": "/v1/embeddings", "ranking": "/v1/ranking"}
SIZE = 2048


def embedding_body(vectors, digits, seed=20261013):
    rnd = random.Random(seed)
    data = [{"index": i, "embedding": [round(rnd.uniform(-0.09, 0.09), digits) for _ in range(SIZE)], "object": "embedding"} for i in range(vectors)]
    return json.dumps({"object": "list", "data": data, "model": "instant/answer", "usage": {"prompt_tokens": 12 * vectors, "total_tokens": 12 * vectors}}, separators=(",", ":")).encode()


def ranking_body(entries, digits, seed=20261013):
    rnd = random.Random(seed)
    ranks = [{"index": i, "logit": round(rnd.uniform(-12.0, 12.0), digits)} for i in range(entries)]
    return json.dumps({"rankings": ranks, "usage": {"prompt_tokens": 0, "total_tokens": 0}}, separators=(",", ":")).encode()


def body_of_about(shape, target_bytes):
    """The body of that shape whose size is nearest to the target: the numbers are printed with more or fewer decimals.
    -> (bytes, decimals used)"""
    kind, count = SHAPES[shape]; make = embedding_body if kind == "embedding" else ranking_body
    best = min(((abs(len(b) - target_bytes), d, b) for d in range(1, 18) for b in (make(count, d),)), key=lambda x: x[:2])
    return best[2], best[1]


def response(body):
    return b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: " + str(len(body)).encode() + b"\r\nConnection: keep-alive\r\n\r\n" + body


def table(targets):
    """-> {path: full HTTP answer}, {shape: {target_bytes, body_bytes, decimals}}"""
    out, rec = {}, {}
    for shape, target in targets.items():
        body, digits = body_of_about(shape, target)
        out["/shape/" + shape] = out[NIM_PATH[SHAPES[shape][0]]] = response(body)
        rec[shape] = {"target_bytes": target, "body_bytes": len(body), "decimals": digits, "served_on": NIM_PATH[SHAPES[shape][0]]}
    return out, rec


READY = response(json.dumps({"object": "health-response", "message": "Service is ready."}).encode())
NOT_FOUND = b"HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\nConnection: keep-alive\r\n\r\n"


def handler(answers):
    async def handle(reader, writer):
        try:
            while True:
                head = await reader.readuntil(b"\r\n\r\n")
                first = head.split(b"\r\n", 1)[0].split(b" ")
                length = 0
                for line in head.split(b"\r\n")[1:]:
                    if line.lower().startswith(b"content-length:"):
                        length = int(line.split(b":", 1)[1])
                if length:
                    await reader.readexactly(length)                 # the whole request is taken before the answer goes out
                path = first[1].decode("ascii", "replace").split("?")[0] if len(first) > 1 else ""
                writer.write(answers.get(path, NOT_FOUND) if first[0] == b"POST" else READY if path.startswith("/v1/health") else NOT_FOUND)
                await writer.drain()
        except (asyncio.IncompleteReadError, asyncio.LimitOverrunError, ConnectionError):
            pass
        finally:
            writer.close()
    return handle


async def serve(answers, port, host="0.0.0.0"):
    return await asyncio.start_server(handler(answers), host, port, limit=2 ** 22)


def parse_targets(text):
    t = {k: int(v) for k, v in (p.split("=") for p in text.split(","))}
    if not t or set(t) - set(SHAPES):
        sys.exit("--bytes takes shape=bytes pairs for: " + ", ".join(SHAPES))
    kinds = [SHAPES[k][0] for k in t]
    if len(kinds) != len(set(kinds)):
        sys.exit("one server takes at most one embeddings shape and one ranking shape")
    return t


async def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--bytes", required=True); ap.add_argument("--port", type=int, default=8000)
    a = ap.parse_args()
    answers, rec = table(parse_targets(a.bytes))
    server = await serve(answers, a.port)
    print(json.dumps({"instant_answer_server": "ready", "port": a.port, "bodies": rec}), file=sys.stderr, flush=True)
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
