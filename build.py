#!/usr/local/bin/python3
"""swapcheck — build a SIGNED swap-sanity report from live Uniswap V3 quotes.

Answers REVENUE.md work-tick queue line: "build the smallest demo for the
highest-ranked surviving path". Path 2 = signed swap-sanity report. The report
shows a REAL >1% discrepancy between the route a wallet would naively take and
the best route, signed with my wallet key (EIP-191 personal_sign) so a reader can
prove the numbers came from me and were not edited after signing.

Read-only: quotes are free eth_calls. No swap, no spend, no key in the browser.
Verify with verify.py (or any ethers verifyMessage).
"""
import datetime
import json
import os
import sys

sys.path.insert(0, "/opt/data/bin")
import treasury as T  # noqa: E402
import routecheck as R  # noqa: E402

CHAIN = "base"
PAIRS = [("DAI", 1000), ("EURC", 1000)]  # human units; real thin-pool demos
HERE = os.path.dirname(os.path.abspath(__file__))
DISCLOSE = ("Autonomous AI agent report. Read-only Uniswap V3 quotes, no trade "
            "executed. Not financial advice. Revenue $0.00 until USDC settles.")


def canonical_bytes(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True).encode("utf-8")


def personal_digest(msg):
    return T.keccak(b"\x19Ethereum Signed Message:\n" + str(len(msg)).encode() + msg)


def collect_pair(chain, sym, amount_human):
    tbl = T.token_table(chain)
    src = T.resolve(chain, sym)
    dst = T.resolve(chain, "USDC")
    amt = T.to_units(amount_human, src[1])

    blk = T.rpc(chain, "eth_getBlockByNumber", ["latest", False])
    base_fee = int(blk["baseFeePerGas"], 16)
    q_eth = R.quote_best(chain, (tbl["WETH"][0], tbl["WETH"][1], "WETH"),
                         (tbl["USDC"][0], tbl["USDC"][1], "USDC"), 10 ** 18)
    eth_usdc = (q_eth[1] / 1e6) if q_eth else 0.0
    gas_swap = base_fee * 2 * 150_000 / 1e18 * eth_usdc
    gas_approve = base_fee * 2 * 60_000 / 1e18 * eth_usdc

    routes = []
    d = R.route_direct(chain, src, dst, amt)
    if d:
        routes.append({"path": d["path"], "hops": 1,
                       "gross_usdc": round(d["out"] / 10 ** d["decimals"], 4),
                       "gas_usd": round(gas_swap + (gas_approve if sym != "WETH" else 0), 4)})
    for b in R.BRIDGES:
        if b == "USDC":
            continue
        v = R.route_via(chain, src, dst, amt, b)
        if v:
            routes.append({"path": v["path"], "hops": 2,
                           "gross_usdc": round(v["out"] / 10 ** v["decimals"], 4),
                           "gas_usd": round(2 * gas_swap + (gas_approve if sym != "WETH" else 0), 4)})
    for r in routes:
        r["net_usdc"] = round(r["gross_usdc"] - r["gas_usd"], 4)
    routes.sort(key=lambda r: r["net_usdc"], reverse=True)
    best, worst = routes[0], routes[-1]
    spread = round(best["net_usdc"] / worst["net_usdc"], 3) if worst["net_usdc"] > 0 else None
    loss = round(best["net_usdc"] - worst["net_usdc"], 4)
    return {
        "sell": sym, "amount_human": amount_human, "buy": "USDC",
        "routes": routes,
        "best": {"path": best["path"], "net_usdc": best["net_usdc"]},
        "worst": {"path": worst["path"], "net_usdc": worst["net_usdc"]},
        "spread_x": spread,
        "wrong_route_loss_usd": loss if loss > 0 else 0.0,
        "verdict": "THIN_POOL_WARNING" if (spread is not None and spread > 1.01) else "OK",
    }


def build_html(env):
    import html
    p = env["payload"]
    now = p["generated_at"]
    pairs = []
    for pr in p["pairs"]:
        rows = "".join(
            "<tr{}><td>{}</td><td class=n>{}</td><td class=n>{}</td><td class=n>{}</td></tr>".format(
                ' class="best"' if r is pr["best"] or r["path"] == pr["best"]["path"] and r["net_usdc"] == pr["best"]["net_usdc"] else "",
                html.escape(" → ".join(r["path"])), r["hops"],
                "{:,.4f}".format(r["gross_usdc"]), "{:,.4f}".format(r["net_usdc"]))
            for r in pr["routes"])
        spread = "{:,.2f}×".format(pr["spread_x"]) if pr["spread_x"] else "n/a"
        pairs.append("""
<section class=pair>
  <h2>{sell} {amt} → {buy} <span class="v {vc}">{verdict}</span></h2>
  <div class=kpis>
    <div><span>best route</span><b>{best}</b></div>
    <div><span>spread best/worst</span><b>{spread}</b></div>
    <div><span>cost of the wrong route</span><b class=loss>${loss}</b></div>
    <div><span>chain block</span><b>{blk}</b></div>
  </div>
  <table><thead><tr><th>route</th><th>hops</th><th>gross USDC</th><th>net USDC</th></tr></thead>
  <tbody>{rows}</tbody></table>
</section>""".format(sell=html.escape(pr["sell"]), amt=pr["amount_human"], buy=pr["buy"],
                     verdict=pr["verdict"], vc="warn" if pr["verdict"] != "OK" else "ok",
                     best=html.escape(" → ".join(pr["best"]["path"])), spread=spread,
                     loss="{:,.2f}".format(pr["wrong_route_loss_usd"]),
                     blk=p["block"]["number"], rows=rows))

    return """<!doctype html><html lang=en><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>swapcheck — signed swap-sanity report</title>
<style>
:root{{--bg:#0b0f14;--card:#131a22;--ink:#e6edf3;--dim:#8b98a5;--line:#26313d;--hi:#4ade80;--warn:#fbbf24;--loss:#f87171}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace}}
main{{max-width:920px;margin:0 auto;padding:34px 20px 60px}}h1{{font-size:26px;margin:0 0 4px}}
.sub{{color:var(--dim);margin-bottom:26px}}a{{color:#7dd3fc}}section.pair{{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:18px 20px;margin:18px 0}}
h2{{font-size:17px;margin:0 0 14px}}.v{{font-size:11px;padding:3px 7px;border-radius:5px;vertical-align:middle}}
.v.warn{{background:#4a3208;color:var(--warn)}}.v.ok{{background:#0f3d24;color:var(--hi)}}
.kpis{{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;margin-bottom:16px}}
.kpis div{{background:#0d1319;border:1px solid var(--line);border-radius:7px;padding:10px}}
.kpis span{{display:block;color:var(--dim);font-size:11px;margin-bottom:4px}}.kpis b{{font-size:15px}}
.loss{{color:var(--loss)}}table{{width:100%;border-collapse:collapse;font-size:13px}}
th{{text-align:left;color:var(--dim);font-weight:400;border-bottom:1px solid var(--line);padding:6px}}
td{{padding:6px;border-bottom:1px solid #1b252f}}.n{{text-align:right}}
tr.best td{{color:var(--hi)}}.meta{{color:var(--dim);font-size:12px;margin-top:22px;word-break:break-all}}
.disc{{border-left:3px solid var(--warn);padding:8px 14px;color:var(--dim);font-size:12px;margin:20px 0}}
code{{background:#0d1319;padding:2px 5px;border-radius:4px}}
</style></head><body><main>
<h1>swapcheck</h1>
<div class=sub>a signed swap-sanity report · generated <b>{now}</b> · chain {chain} (id {cid})</div>
<div class=disc>{disc}</div>
{pairs}
<div class=meta>
<b>signer</b> <code>{signer}</code><br>
<b>scheme</b> {scheme}<br>
<b>signature</b> <code>{sig}</code><br>
<b>source</b> Uniswap V3 QuoterV2 via public RPC (free eth_call). Quotes are a snapshot at block {blk}; pools move.
Verify with <code>verify.py report.json</code> — any edit to a number breaks the signature.
</div>
</main></body></html>""".format(now=now, chain=p["chain"], cid=p["chain_id"], disc=DISCLOSE,
                               pairs="".join(pairs), signer=p["signer"], scheme=env["scheme"],
                               sig=env["signature"], blk=p["block"]["number"])


def main():
    mnem = T.load_key()
    signer = T.derive_address(mnem)
    priv = T.private_key_bytes(mnem)
    pairs = [collect_pair(CHAIN, sym, amt) for sym, amt in PAIRS]
    blk = T.rpc(CHAIN, "eth_getBlockByNumber", ["latest", False])
    payload = {
        "schema": "swapcheck/1",
        "generated_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "chain": CHAIN, "chain_id": T.CHAINS[CHAIN]["id"],
        "signer": signer,
        "block": {"number": int(blk["number"], 16), "base_fee_wei": int(blk["baseFeePerGas"], 16)},
        "quote_source": "Uniswap V3 QuoterV2 via public RPC (free eth_call)",
        "pairs": pairs,
        "disclosure": DISCLOSE,
    }
    digest = personal_digest(canonical_bytes(payload))
    sig = bytes(T.PrivateKey(priv).sign_recoverable(digest, hasher=None))
    signature = "0x" + sig[:64].hex() + format(sig[64], "02x")
    env = {"schema": "swapcheck-envelope/1",
           "scheme": "EIP-191 personal_sign / secp256k1 over canonical JSON (sort_keys, compact)",
           "signature": signature, "payload": payload}

    jpath = os.path.join(HERE, "report.json")
    hpath = os.path.join(HERE, "index.html")
    served = "/opt/data/serve/swapcheck.html"
    with open(jpath, "w") as f:
        json.dump(env, f, indent=2)
    htm = build_html(env)
    with open(hpath, "w") as f:
        f.write(htm)
    with open(served, "w") as f:
        f.write(htm)
    print("wrote", jpath, hpath, served)
    for pr in pairs:
        print("  {sell} {amt}: spread {sp}x, wrong-route cost ${loss}, {verdict}".format(
            sell=pr["sell"], amt=pr["amount_human"], sp=pr["spread_x"],
            loss=pr["wrong_route_loss_usd"], verdict=pr["verdict"]))
    print("  signer", signer, "signature", signature[:18] + "...")


if __name__ == "__main__":
    main()
