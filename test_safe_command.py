import subprocess
import sys

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

# 1. Stage all tracked and new files
run_cmd(["git", "add", "."])

# 2. Check status before commit
run_cmd(["git", "status", "--short"])

# 3. Commit
commit_msg = "fix: resolve recording save permission error & non-blocking video export with quick export feature"
run_cmd(["git", "commit", "-m", commit_msg])

# 4. Push to remote main
print("Pushing to origin main...")
run_cmd(["git", "push", "origin", "main"])

print("Git push completed successfully!")
