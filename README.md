# Sandboxed

Python module with utilities to jail execution with limited privileges, filesystem, network and resources.

Inspired by [Da_Blitz's work on Asylum](http://code.pocketnix.org/asylum). I made this to learn ctypes and how namespaces/cgroups and parts of Linux kernel work by trying to use it directly instead of just reading about it.

It is unfinished, has no setup.(py|ini) yet.

To use it, you need new Linux kernel with namespaces compiled in (`CONFIG_NAMESPACES`, `CONFIG_*_NS`) and be able to run as root (`CAP_SYS_ADMIN` privilege)

## Examples

You have two usage examples: jail.py and remote_exec.py. Both need changes in code if you want to run it (changing user and group names, changing path to python distribution)

### jail.py - jailed REPL

This script jails itself and starts interactive interpreter, so you can play around.

Inside you will have:

1. Access only to basic read-only filesystem
1. No access to network interfaces
1. No access to other processes
1. Restriction to one process (fork fails, threading will fail)

To achieve this it...

1. Mounts temporary tmpfs in `/tmp`
1. Mounts Python library inside (read-only bind), so after jailing we can still import modules
1. Do process clone with new namespaces
1. Sets hostname
1. Pivots root filesystem (makes mounted tmpfs as root)
1. Mounts `/proc` and optionally simple `/dev` and `/cgroup`
1. Umounts all filesystems except needed
1. Remounts fs read-only
1. setgid/setuid
1. Enters REPL

### remote_exec.py - jailed remote executor

It starts preforked unix-socket server. After connect, it will execute `/usr/bin/main.py` inside jailed worker, pipe to its stdin anythin that it reads from socket (until nullchar) and pipe back to socket anything this script write to stdout. After script quits, it sends nullchar to client and closes connection.

To run it you will need to:

1. Get your own version of Python in one place (compile it and install it in folder which can be mounted inside jail, along with all required shared libraries). You may also want to remove _ctypes module.
1. Put in its `/bin` a script `named main.py` - it will be executed inside jail for each worker.
1. Set path to this Python distribution inside `remote_exec.py`

It works in similar way as jail.py, but instead of mounting just Pythons stdlib, it mounts whole python distribution. Also, it limits time of executed script to six seconds - after this time script is killed.

# Why?

Mostly for fun, for educational purposes, and to try to make online tester for Pyhaa.

