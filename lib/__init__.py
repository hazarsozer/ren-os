"""
lib/ — framework-wide core package (ADR-031, solo-first pivot).

Top-level package holding the path/handle/schema resolution that the *whole*
framework depends on, extracted from the former feed.config so it survives the
removal of the Activity Feed module. The plugin root is already on sys.path (the
wake-up hook's _ensure_plugin_root_on_path + skills' REPO_ROOT inserts), so
`import lib.sf_paths` resolves from the packaged plugin root in the installed runtime.
"""
