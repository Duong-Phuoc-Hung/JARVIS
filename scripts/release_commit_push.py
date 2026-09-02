import subprocess
import sys

# CREATE_NO_WINDOW (R2 compliance): suppress CMD windows on Windows
_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


def main():
    print("=== Staging changes ===")
    res1 = subprocess.run(
        ["git", "add", "-A"], capture_output=True, text=True,
        creationflags=_NO_WINDOW,  # CREATE_NO_WINDOW (R2 compliance)
    )
    print("STDOUT:", res1.stdout)
    print("STDERR:", res1.stderr)
    print("RET:", res1.returncode)

    print("\n=== Committing ===")
    res2 = subprocess.run(
        ["git", "commit", "-m", "feat: v4.7.0 - Sprint 2 Acoustic & UX Hardening"],
        capture_output=True, text=True,
        creationflags=_NO_WINDOW,  # CREATE_NO_WINDOW (R2 compliance)
    )
    print("STDOUT:", res2.stdout)
    print("STDERR:", res2.stderr)
    print("RET:", res2.returncode)

    print("\n=== Pushing to origin main ===")
    res3 = subprocess.run(
        ["git", "push", "origin", "main"], capture_output=True, text=True,
        creationflags=_NO_WINDOW,  # CREATE_NO_WINDOW (R2 compliance)
    )
    print("STDOUT:", res3.stdout)
    print("STDERR:", res3.stderr)
    print("RET:", res3.returncode)

    print("\n=== Git Status ===")
    res4 = subprocess.run(
        ["git", "status"], capture_output=True, text=True,
        creationflags=_NO_WINDOW,  # CREATE_NO_WINDOW (R2 compliance)
    )
    print("STDOUT:\n", res4.stdout)
    print("STDERR:\n", res4.stderr)

    print("\n=== Git Log -1 ===")
    res5 = subprocess.run(
        ["git", "log", "-1"], capture_output=True, text=True,
        creationflags=_NO_WINDOW,  # CREATE_NO_WINDOW (R2 compliance)
    )
    print("STDOUT:\n", res5.stdout)
    print("STDERR:\n", res5.stderr)


if __name__ == "__main__":
    main()
