"""Link static/custom.css into the built site.  Usage: python tools/inject_custom_css.py dist

JupyterLite has no supported way to recolour a specific toolbar icon --
the theme "CSS overrides" setting (@jupyterlab/apputils-extension:themes)
only covers fonts and the error-output background -- so this copies our
stylesheet into each built app and links it from index.html directly.
Run after `jupyter lite build`.
"""
import shutil
import sys
from pathlib import Path

APPS = ["lab"]  # add "notebooks", "tree", etc. here if those apps need it too
LINK_TAG = '<link rel="stylesheet" href="./custom.css">'


def main(dist_dir):
    dist_dir = Path(dist_dir)
    css_src = Path(__file__).parent.parent / "static" / "custom.css"

    for app in APPS:
        app_dir = dist_dir / app
        if not app_dir.is_dir():
            print(f"skipping {app}: {app_dir} does not exist")
            continue

        shutil.copyfile(css_src, app_dir / "custom.css")

        index_html = app_dir / "index.html"
        html = index_html.read_text()
        if LINK_TAG not in html:
            html = html.replace("</head>", f"  {LINK_TAG}\n  </head>", 1)
            index_html.write_text(html)
        print(f"linked custom.css into {index_html}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "dist")
