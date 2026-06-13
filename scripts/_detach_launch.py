#!/usr/bin/env python3
"""Double-fork launcher: detach a command into its own session so it
survives the parent tool's process-group cleanup. macOS lacks setsid."""
import os
import sys

def main():
    log = sys.argv[1]
    cmd = sys.argv[2:]
    # First fork
    if os.fork() > 0:
        os._exit(0)
    os.setsid()  # new session, detach from controlling terminal/pgroup
    # Second fork
    if os.fork() > 0:
        os._exit(0)
    # Grandchild: redirect fds and exec
    devnull = os.open(os.devnull, os.O_RDONLY)
    os.dup2(devnull, 0)
    fd = os.open(log, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
    os.dup2(fd, 1)
    os.dup2(fd, 2)
    os.execv(cmd[0], cmd)

if __name__ == "__main__":
    main()
