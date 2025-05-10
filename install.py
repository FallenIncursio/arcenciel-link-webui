import launch # type: ignore

req_file = "requirements.txt"
with open(req_file) as f:
    packages = [l.strip() for l in f if l.strip() and not l.startswith("#")]

for p in packages:
    if not launch.is_installed(p):
        launch.run_pip(f"install {p}", f"arcenciel-link requirement: {p}")