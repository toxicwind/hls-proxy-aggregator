#!/usr/bin/env python3
"""
auto_lint.py — Validates Python syntax, auto-fixes common issues, reports.
Usage: python3 -m helpers.auto_lint src/ osint/
"""
import ast, sys, os, re

ISSUES = []

def check_syntax(path):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            source = f.read()
        ast.parse(source)
        return True, "OK"
    except SyntaxError as e:
        return False, f"SyntaxError line {e.lineno}: {e.msg}"
    except Exception as e:
        return False, str(e)

def fix_common_issues(source):
    source = re.sub(r'except\s*:', 'except Exception:', source)
    source = re.sub(
        r'json\.dump\(([^,]+),\s*([^,]+),\s*ensure_ascii=False,\s*indent=\d+\)',
        r'json.dump(\1, \2, ensure_ascii=False, separators=(",", ":"))',
        source
    )
    source = re.sub(
        r'json\.dump\(([^,]+),\s*([^,]+)\)',
        r'json.dump(\1, \2, ensure_ascii=False, separators=(",", ":"))',
        source
    )
    return source

def lint_file(path):
    ok, msg = check_syntax(path)
    rel = os.path.relpath(path)
    if ok:
        print(f"  [OK] {rel}")
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            orig = f.read()
        fixed = fix_common_issues(orig)
        if fixed != orig:
            with open(path, "w", encoding="utf-8") as f:
                f.write(fixed)
            print(f"  [FIX] {rel}")
        return True
    else:
        print(f"  [ERR] {rel}: {msg}")
        ISSUES.append((rel, msg))
        return False

def main():
    targets = sys.argv[1:] or ["src", "osint"]
    total = 0; passed = 0
    for t in targets:
        for root, _, files in os.walk(t):
            for fn in files:
                if fn.endswith(".py"):
                    total += 1
                    if lint_file(os.path.join(root, fn)):
                        passed += 1
    print(f"\nLint: {passed}/{total} passed")
    if ISSUES:
        for f, m in ISSUES:
            print(f"  {f}: {m}")
        sys.exit(1)

if __name__ == "__main__":
    main()
