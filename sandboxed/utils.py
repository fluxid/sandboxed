#coding:utf8

'''
Convenience utilities
'''

import distutils.sysconfig
import errno
import os
import os.path
import signal
import stat
import sys
import time

from . import lowlevel
from . import const

__all__ = (
    'clone_and_wait',
    'mount_bind',
    'mount_cgroup',
    'mount_proc',
    'mount_python_lib',
    'mount_simple_dev',
    'mount_tmpfs',
    'patient_terminate',
    'read_mounts',
    'try_kill',
    'try_mkdir',
    'umount_all',
    'wait_for_pid',
)

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

def mount_simple_dev(path = '/dev'):
    '''
    Creates mountpoint and mounts cgroup fs in it
    '''
    try_mkdir(path)
    flags = const.MS_NOEXEC | const.MS_NOSUID | const.MS_NOATIME
    lowlevel.mount('simple_dev', path, 'tmpfs', flags, 'size=1024k')
    os.mknod(os.path.join(path, 'null'), 0o777, stat.S_IFCHR | os.makedev(1, 3))
    os.mknod(os.path.join(path, 'zero'), 0o777, stat.S_IFCHR | os.makedev(1, 5))

def mount_python_lib(path, no_exec = False):
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

    flags = const.MS_NODEV | const.MS_NOSUID | const.MS_NOATIME
    if no_exec:
        flags |= const.MS_NOEXEC
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

def clone_and_wait(callback, flags):
    pid = lowlevel.clone(flags)
    assert pid is not None
    if pid:
        def handle_signal(signum, frame):
            patient_terminate(pid, wait_flags = const.WALL)

        old_term = signal.getsignal(signal.SIGTERM)
        old_int = signal.getsignal(signal.SIGINT)
        signal.signal(signal.SIGTERM, handle_signal)
        signal.signal(signal.SIGINT, handle_signal)

        wait_for_pid(pid, flags = const.WALL)

        signal.signal(signal.SIGTERM, old_term)
        signal.signal(signal.SIGINT, old_int)
    else:
        status = 1
        try:
            if flags ^ const.CLONE_NEWPID:
                assert lowlevel.getpid() == 1
            status = callback()
            status = int(status) if status else 0
        except:
            sys.excepthook(*sys.exc_info())
        finally:
            os._exit(status)
        
def wait_for_pid(pid, tries = 0, sleep = 0.1, flags = 0):
    '''
    Waits for child pid
    Returns True if childs does not exist or waiting for it finished.
    Returns False if tries > 0 and child doesn't quit or if wait
    was interrupted.
    Other children we wait for are ignored quietly.

    `tries` sets count of times we try to wait for child.
    `sleep` sets time we spend sleeping between waiting for child.
    If `tries` is zero, we wait forever, until child quits.
    '''
    hang = not tries
    if not hang:
        flags |= os.WNOHANG
    while hang or tries:
        try:
            pid2, _ = os.waitpid(pid, flags)
        except OSError as exc:
            if exc.errno == errno.ECHILD:
                return True
            elif exc.errno == errno.EINTR:
                return False
            raise
        if pid2 == pid:
            return True

        if not hang:
            if tries:
                time.sleep(sleep)
            tries -= 1
    return False

def try_kill(pid, signal):
    '''
    Tries to kill child.
    Returns True if child does not exist.
    Returns False otherwise.
    '''
    try:
        os.kill(pid, signal)
    except OSError as exc:
        if exc.errno == errno.ECHILD:
            return True
        raise
    return False

def patient_terminate(pid, wait_flags = 0):
    '''
    Sends SIGTERM, waits a second, sends SKIGKILL
    '''
    if wait_for_pid(pid, 1, flags = wait_flags):
        return
    try_kill(pid, signal.SIGTERM)
    if wait_for_pid(pid, 10, flags = wait_flags):
        return
    try_kill(pid, signal.SIGKILL)
    wait_for_pid(pid, flags = wait_flags)

