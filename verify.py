#!/usr/local/bin/python3
"""verify.py — independently verify a swapcheck report's signature and binding.

Usage:  verify.py [report.json]        (reads stdin if no path)
Exit 0 = PASS, 1 = FAIL. No wallet key needed; no network needed.
Matches ethers `verifyMessage(canonicalJson, signature)`.
"""
import json
import sys

sys.path.insert(0, "/opt/data/bin")
import treasury as T  # noqa: E402
from coincurve import PublicKey  # noqa: E402


def canonical_bytes(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True).encode("utf-8")


def personal_digest(msg):
    return T.keccak(b"\x19Ethereum Signed Message:\n" + str(len(msg)).encode() + msg)


def recover(digest, signature):
    if not (isinstance(signature, str) and signature.startswith("0x") and len(signature) == 132):
        raise ValueError("bad signature shape")
    b = bytes.fromhex(signature[2:])
    recid = b[64]
    if recid >= 4:
        raise ValueError("bad recovery id")
    pub = PublicKey.from_signature_and_message(b[:64] + bytes([recid]), digest, hasher=None)
    return "0x" + T.keccak(pub.format(compressed=False)[1:])[-20:].hex()


def verify(env):
    errs = []
    if env.get("schema") != "swapcheck-envelope/1":
        errs.append("wrong envelope schema")
    p = env.get("payload", {})
    if p.get("schema") != "swapcheck/1":
        errs.append("wrong payload schema")
    digest = personal_digest(canonical_bytes(p))
    try:
        recovered = recover(digest, env.get("signature", ""))
    except Exception as e:  # noqa: BLE001
        recovered = None
        errs.append("signature unrecoverable: " + str(e))
    declared = p.get("signer", "")
    if recovered and recovered.lower() != str(declared).lower():
        errs.append("signer mismatch: recovered {} != declared {}".format(recovered, declared))
    # structural checks: every pair must carry signed route math, not just a number
    pairs = p.get("pairs")
    if not isinstance(pairs, list) or not pairs:
        errs.append("no pairs")
    else:
        for pr in pairs:
            for k in ("sell", "amount_human", "routes", "best", "worst", "spread_x",
                      "wrong_route_loss_usd", "verdict"):
                if k not in pr:
                    errs.append("pair missing " + k)
            if pr.get("routes"):
                for r in pr["routes"]:
                    if not all(k in r for k in ("path", "gross_usdc", "gas_usd", "net_usdc")):
                        errs.append("route missing fields")
    if "generated_at" not in p or "block" not in p:
        errs.append("report not dated / not block-bound")
    if "$0.00" not in p.get("disclosure", ""):
        errs.append("revenue disclosure missing")
    ok = not errs
    return ok, recovered, errs


def main():
    raw = open(sys.argv[1]).read() if len(sys.argv) > 1 else sys.stdin.read()
    try:
        env = json.loads(raw)
    except Exception as e:  # noqa: BLE001
        print("FAIL: invalid JSON:", e)
        return 1
    ok, recovered, errs = verify(env)
    if ok:
        print("PASS — signature recovers declared signer", recovered)
        print("       canonical payload intact; date + block + disclosure bound")
        return 0
    print("FAIL:", "; ".join(errs))
    return 1


if __name__ == "__main__":
    sys.exit(main())
