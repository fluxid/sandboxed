Sandboxed
=========

Python script to jail execution with limited privileges, filesystem, network and resources.

Inspired by [Da_Blitz's work on Asylum](http://code.pocketnix.org/asylum). I made this to learn ctypes and how namespaces/cgroups and parts of Linux kernel work by trying to use it directly instead of just reading about it.

It is unfinished, has no setup.(py|ini) yet.

How to run
----------

You need new Linux kernel with cgroups and namespaces compiled in (`CONFIG_CGROUPS`, `CONFIG_CGROUPS_*`, `CONFIG_NAMESPACES`, `CONFIG_*_NS`) and be able to run as root.
Try to run example jailed REPL (you may want change code in `jail.py` to change user/group names):

    % sudo python3 jail.py

A Python REPL will appear.

Inside you will have:

1. Access only to basic read-only filesystem
1. No access to network interfaces
1. No access to other processes
1. No privileges
1. Restriction to one process (fork fails, threading will fail)

Why?
----

Mostly for fun, for educational purposes, and to try to make online tester for Pyhaa.

