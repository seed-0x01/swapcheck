#!/usr/local/bin/python3
"""Fixtures for swapcheck: prove the signature actually binds every number."""
import copy
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import verify as V  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = json.load(open(os.path.join(HERE, "report.json")))
results = []


def check(name, env, expect):
    try:
        ok, rec, errs = V.verify(env)
    except Exception as e:  # noqa: BLE001
        ok, errs = False, [str(e)]
    passed = (ok == expect)
    results.append((name, passed, "ok" if ok else ";".join(errs)[:70]))


# 1. genuine report passes
check("valid report", BASE, True)
# 2. key reordering still passes (canonicalization works)
e = copy.deepcopy(BASE); e["payload"] = dict(reversed(list(e["payload"].items())))
check("key order irrelevant", e, True)
# 3. tamper a signed net_usdc -> fail
e = copy.deepcopy(BASE); e["payload"]["pairs"][0]["routes"][0]["net_usdc"] += 0.01
check("tampered net_usdc", e, False)
# 4. tamper the spread -> fail
e = copy.deepcopy(BASE); e["payload"]["pairs"][0]["spread_x"] += 1
check("tampered spread", e, False)
# 5. tamper the generated_at date -> fail
e = copy.deepcopy(BASE); e["payload"]["generated_at"] = "2020-01-01T00:00:00Z"
check("tampered date", e, False)
# 6. tamper declared signer -> fail
e = copy.deepcopy(BASE); e["payload"]["signer"] = "0x" + "0" * 40
check("tampered signer", e, False)
# 7. corrupt signature byte -> fail
e = copy.deepcopy(BASE); e["signature"] = e["signature"][:-2] + "00"
check("corrupt signature", e, False)
# 8. drop disclosure -> fail
e = copy.deepcopy(BASE); e["payload"]["disclosure"] = ""
check("revenue disclosure required", e, False)
# 9. mismatched block -> fail
e = copy.deepcopy(BASE); e["payload"]["block"]["number"] += 1
check("tampered block", e, False)
# 10. empty pairs -> fail
e = copy.deepcopy(BASE); e["payload"]["pairs"] = []
check("no pairs", e, False)

for name, passed, info in results:
    print(("PASS" if passed else "FAIL"), "-", name, "|", info)
npass = sum(1 for _, p, _ in results if p)
print("{}/{} fixtures PASS".format(npass, len(results)))
sys.exit(0 if npass == len(results) else 1)
