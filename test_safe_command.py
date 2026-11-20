import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

def run_cmd(args):
    print(f"Running: {' '.join(args)}")
    res = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if res.stdout.strip():
        print("STDOUT:\n", res.stdout.strip())
    if res.stderr.strip():
        print("STDERR:\n", res.stderr.strip())
    if res.returncode != 0:
        print(f"Failed with code {res.returncode}")
        sys.exit(res.returncode)
    return res

run_cmd(["git", "add", "."])
run_cmd(["git", "status", "--short"])

commit_msg = "feat: auto-detect native audio format (GetMixFormat) & multi-output simultaneous loopback capture (Method B)"
run_cmd(["git", "commit", "-m", commit_msg])

print("Pushing to origin main...")
run_cmd(["git", "push", "origin", "main"])
print("Git push completed successfully!")
