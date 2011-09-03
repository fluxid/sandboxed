#coding:utf8

'''
Convenience utilities
'''

import errno
import os
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

