#!/usr/bin/env python3
import subprocess
import sys
import os
import tempfile
import atexit
import shutil

def run_ssh_with_control(host, user, cmd, control_path):
    full_cmd = [
        "ssh",
        "-o", f"ControlPath={control_path}",
        "-o", "ControlMaster=no",
        f"{user}@{host}",
        cmd
    ]
    result = subprocess.run(full_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"SSH error: {result.stderr.strip()}", file=sys.stderr)
        sys.exit(1)
    return result.stdout

def setup_ssh_control(host, user, control_path):
    # Establish master connection (this is where you enter password/2FA)
    master_cmd = [
        "ssh",
        "-fN",  # Fork to background after auth
        "-o", "ControlMaster=yes",
        "-o", f"ControlPath={control_path}",
        "-o", "ControlPersist=300",  # Keep alive 5 mins
        f"{user}@{host}"
    ]
    result = subprocess.run(master_cmd)
    if result.returncode != 0:
        print("Failed to establish SSH control connection.", file=sys.stderr)
        sys.exit(1)

    # Ensure cleanup
    def cleanup():
        subprocess.run(["ssh", "-O", "exit", "-o", f"ControlPath={control_path}", f"{user}@{host}"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    atexit.register(cleanup)

def get_remote_files(host, user, remote_path, control_path):
    # Escape single quotes in path for shell safety
    safe_path = remote_path.replace("'", "'\"'\"'")
    cmd = f"find '{safe_path}' -type f -exec stat --format='%s %n' {{}} \\;"
    output = run_ssh_with_control(host, user, cmd, control_path)
    files = []
    for line in output.strip().splitlines():
        if not line:
            continue
        parts = line.split(' ', 1)
        if len(parts) != 2:
            continue
        size_str, path = parts
        try:
            size = int(size_str)
        except ValueError:
            continue
        files.append((path, size))
    return files

def format_size(bytes_):
    for unit in ['B', 'K', 'M', 'G', 'T']:
        if bytes_ < 1024.0:
            return f"{bytes_:.1f}{unit}"
        bytes_ /= 1024.0
    return f"{bytes_:.1f}P"

def fuzzy_match(query, path):
    query = query.lower()
    path = path.lower()
    it = iter(path)
    return all(c in it for c in query)

def prompt_local_dir():
    default = os.path.join(os.getcwd(), "downloaded")
    print(f"📁 Enter local download directory [default: {default}]:")
    user_input = input("> ").strip()
    return user_input if user_input else default

def main():
    if len(sys.argv) != 4:
        print("Usage: python3 ssh-fuzzy-copy.py <user> <host> <remote_path>", file=sys.stderr)
        sys.exit(1)

    user, host, remote_path = sys.argv[1], sys.argv[2], sys.argv[3]

    # Create temp dir for control socket
    temp_dir = tempfile.mkdtemp()
    control_path = os.path.join(temp_dir, "ssh_mux_%h_%p_%r")

    def cleanup_temp():
        shutil.rmtree(temp_dir, ignore_errors=True)
    atexit.register(cleanup_temp)

    print("🔐 Establishing shared SSH connection (enter password once)...")
    setup_ssh_control(host, user, control_path)

    print("📡 Fetching remote file list...")
    files = get_remote_files(host, user, remote_path, control_path)
    if not files:
        print("No files found.")
        return

    files.sort()
    print(f"✅ Found {len(files)} files. Enter a fuzzy search query (or press Enter for all):")
    query = input("> ").strip()

    filtered = [(p, s) for p, s in files if fuzzy_match(query, p)] if query else files

    if not filtered:
        print("No files match your query.")
        return

    print(f"\n📋 {len(filtered)} file(s) to consider:\n")
    total_size = 0
    for path, size in filtered:
        print(f"{format_size(size):>8}  {path}")
        total_size += size
    print(f"\n📦 Total size: {format_size(total_size)}")

    local_dir = prompt_local_dir()
    os.makedirs(local_dir, exist_ok=True)
    print(f"\n❓ Proceed with download to '{local_dir}'? (y/N): ", end="")
    choice = input().strip().lower()
    if choice not in ('y', 'yes'):
        print("CloseOperation: Dry run complete. No files copied.")
        return

    print(f"\n📥 Downloading {len(filtered)} file(s)...")
    for path, _ in filtered:
        remote_spec = f"{user}@{host}:{path}"
        basename = os.path.basename(path)
        dest = os.path.join(local_dir, basename)

        # Avoid overwrites
        counter = 1
        orig_dest = dest
        while os.path.exists(dest):
            root, ext = os.path.splitext(orig_dest)
            dest = f"{root}_{counter}{ext}"
            counter += 1

        print(f"  → {dest}")
        result = subprocess.run([
            "scp",
            "-o", f"ControlPath={control_path}",
            "-o", "ControlMaster=no",
            remote_spec,
            dest
        ])
        if result.returncode != 0:
            print(f"⚠️  Failed to copy {path}", file=sys.stderr)

    print("\n✅ Done.")

if __name__ == "__main__":
    main()
