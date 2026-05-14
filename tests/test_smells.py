"""Smoke tests for the smells scanner."""
from pr_audit.smells import scan_diff_for_smells


def test_bare_except():
    diff = """+def foo():
+    try:
+        bar()
+    except:
+        pass
"""
    flags = scan_diff_for_smells(diff)
    assert any(f.startswith("bare_except") for f in flags)


def test_hardcoded_secret():
    diff = """+API_KEY = "sk-proj-abc123def456ghi789jkl012"
"""
    flags = scan_diff_for_smells(diff)
    assert any(f.startswith("hardcoded_secret") for f in flags)


def test_debug_print():
    diff = """+    print("debug:", x)
+    console.log("hello");
"""
    flags = scan_diff_for_smells(diff)
    assert any(f.startswith("debug_print") for f in flags)


def test_no_smells():
    diff = """+def hello():
+    return "world"
"""
    flags = scan_diff_for_smells(diff)
    assert flags == []
