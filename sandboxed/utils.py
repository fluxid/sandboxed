#coding:utf8

'''
Convenience utilities
'''

import distutils.sysconfig
import errno
import os
import os.path
import time

from . import lowlevel
from . import const

def try_mkdir(path):
    '''
    Wrapper of `os.mkdir`
    Ignores error if directory exists
    '''
    try:
        os.mkdir(path)
    except OSError as exc:
        if exc.errno != errno.EEXIST:
            raise

def mount_tmpfs(size, path, flags = 0):
    '''
    Mount tmpfs filesystem with size of `size` kilobytes in given path.
    NODEV, NOEXEC, NOSUID and NOATIME flags are added by default.
    '''
    size = int(size)
    flags |= const.MS_NODEV | const.MS_NOEXEC | const.MS_NOSUID | const.MS_NOATIME
    lowlevel.mount('tmpfs', path, 'tmpfs', flags, 'size={}K'.format(size))

def mount_bind(source, destination, flags = 0):
    '''
    Mountbind source directory in given destination
    '''
    flags |= const.MS_BIND
    lowlevel.mount(source, destination, 'none', flags, None)

def mount_proc(path = '/proc'):
    '''
    Creates mountpoint and mounts proc fs in it
    '''
    try_mkdir(path)
    lowlevel.mount('proc', path, 'proc', 0, None)

def mount_cgroup(path = '/cgroup'):
    '''
    Creates mountpoint and mounts cgroup fs in it
    '''
    try_mkdir(path)
    lowlevel.mount('cgroup', path, 'cgroup', 0, None)

def mount_python_lib(path):
    '''
    Uses bind to mount Python standard library in given path.

    When path becomes new root, Python library will have the same path,
    so no major modifications in sys.path will be needed.

    Returns two paths in 2tuple: original path to Python library and path of
    mountpoint, to be unmounted when no longer needed.
    '''
    pylib = distutils.sysconfig.get_python_lib(standard_lib=True)
    pylib = os.path.realpath(pylib)
    pylib_mount = os.path.join(path, pylib[1:] if pylib.startswith('/') else pylib)
    try:
        os.makedirs(pylib_mount, exist_ok=True)
    except TypeError:
        # exist_ok since Python 3.2
        os.makedirs(pylib_mount)

    flags = const.MS_NODEV | const.MS_NOEXEC | const.MS_NOSUID | const.MS_NOATIME
    mount_bind(pylib, pylib_mount, flags)
    # Binds can be made read-only only after remount, not on first mount...
    flags |= const.MS_REMOUNT | const.MS_RDONLY
    mount_bind(pylib, pylib_mount, flags)

    return (pylib, pylib_mount)

def read_mounts():
    '''
    Read and split lines from /proc/mounts
    '''
    with open('/proc/mounts', 'r') as fp:
        return [
            line.split(' ')
            for line in fp.readlines()
        ]

def umount_all(except_mounts=None, tries=5):
    '''
    Umount all filesystems we can, except mountpoints listed
    in `except_mounts`.
    `tries` argument set how many times we try to umount one
    filesystem.
    '''
    except_mounts = set(except_mounts or [])
    unmounted = 1
    while tries and unmounted:
        tries -= 0
        unmounted = 0

        mounts = sorted(
            (
                line[1]
                for line in read_mounts()
                if line[1] not in except_mounts
            ),
            key = lambda x: -len(x)
        )

        for mount in mounts:
            try:
                lowlevel.umount(mount)
            except OSError:
                unmounted += 1

    if unmounted:
        time.sleep(0.05)

