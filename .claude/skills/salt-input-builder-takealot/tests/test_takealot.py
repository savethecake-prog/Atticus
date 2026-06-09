"""Self-contained tests for the Takealot exporter helpers (no external files)."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import tal_export as T

TREES = {"105": [{"main": "Computer Components (123)", "lowest": "Power Supplies (456)"},
                 {"main": "Computer Components (123)", "lowest": "CPU Coolers (789)"}],
         "120": [{"main": "Gaming Furniture (321)", "lowest": "Gaming Chairs (654)"},
                 {"main": "Gaming Furniture (321)", "lowest": "Gaming Desks (987)"}]}

def run():
    p = f = 0
    def ok(name, cond):
        nonlocal p, f
        if cond: p += 1
        else: f += 1; print("  FAIL:", name)

    ok("tsin -> edit_request", T.route_product("55225399", "anything", TREES) == "edit_request")
    ok("no tsin + components -> 105", T.route_product(None, "Power Supplies", TREES) == "loadsheet_105")
    ok("no tsin + cpu cooler -> 105", T.route_product("", "CPU Coolers", TREES) == "loadsheet_105")
    ok("no tsin + gaming chair -> 120", T.route_product(None, "Gaming Chairs", TREES) == "loadsheet_120")
    ok("no tsin + gaming desk -> 120", T.route_product(None, "Gaming Desks", TREES) == "loadsheet_120")
    ok("unknown category -> unrouted", T.route_product(None, "Submarine Parts", TREES) == "unrouted")

    okv, _, flag = T.enforce_text_length("x" * 70, 75); ok("title 70<=75 ok", okv and flag is None)
    okv, val, flag = T.enforce_text_length("x" * 130, 110); ok("subtitle 130>110 flagged", (not okv) and val == "x" * 130 and flag)
    okv, _, _ = T.enforce_text_length("1234567890123456789012", 20); ok("barcode 22>20 flagged", not okv)
    okv, _, _ = T.enforce_text_length(None, 75); ok("blank passes", okv)

    okv, _ = T.check_dropdown("Limited", ["Limited", "Manufacturer"]); ok("dropdown in-list ok", okv)
    okv, fl = T.check_dropdown("Lifetime", ["Limited", "Manufacturer"]); ok("dropdown off-list flagged", (not okv) and fl)
    okv, _ = T.check_dropdown("", ["Limited"]); ok("dropdown blank skipped", okv)

    print(f"Takealot exporter: {p} passed / {f} failed")
    return f == 0

if __name__ == "__main__":
    sys.exit(0 if run() else 1)
