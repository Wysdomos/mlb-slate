"""
build_py_patch.py
=================
Add build_streaks to the main pipeline in build.py

FIND the section that calls the builders, e.g.:
    import build_day46
    import build_editorial
    build_day46.build(...)
    build_editorial.build(...)

ADD after those calls:
    import build_streaks
    build_streaks.build()

If build.py uses subprocess instead of imports, e.g.:
    subprocess.run(['python3', 'build_day46.py'], check=True)
    subprocess.run(['python3', 'build_editorial.py'], check=True)

ADD:
    subprocess.run(['python3', 'build_streaks.py'], check=True)

Also ensure streaks.html gets synced to GitHub Pages.
In sync.py (or wherever output files are listed), add 'streaks.html'
to the list of files to push/deploy.

If sync.py uses a glob like *.html it's already covered.
"""
