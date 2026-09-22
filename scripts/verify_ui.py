#!/usr/bin/env python3
import urllib.request

def main():
    h = urllib.request.urlopen("http://127.0.0.1:8000/").read().decode()
    c = urllib.request.urlopen("http://127.0.0.1:8000/admin.css").read().decode()
    j = urllib.request.urlopen("http://127.0.0.1:8000/admin.js").read().decode()
    checks = {
        "ainovel_html": "爱小说" in h,
        "theme_select": "theme-select" in h,
        "drawer_resize": "drawer-resize" in h,
        "grid_size": "grid-size" in h,
        "list_wrap": "list-wrap" in h,
        "light_theme_css": 'data-theme="light"' in c,
        "dark_theme_css": 'data-theme="dark"' in c,
        "book_row_js": "book-row" in j,
        "applyTheme_js": "applyTheme" in j,
        "initDrawerResize_js": "initDrawerResize" in j,
    }
    for k, v in checks.items():
        print(("PASS" if v else "FAIL"), k)
    print("RESULT", "ALL PASS" if all(checks.values()) else "HAS FAILURES")

if __name__ == "__main__":
    main()
