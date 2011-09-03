#coding:utf8

'''
Create calls to standard library and syscalls.
Description of those calls is available in `man`.
'''

import ctypes as ct

from . import const
from .ccall import ccall, syscall

__all__ = (
    'getpid',
    'getppid',
    'pivot_root',
    'clone',
    'mount',
    'umount',
    'umount2',
    'sethostname',
    'gethostname',
)

# C Calls
getpid = syscall(const.SYS_getpid)
getppid = syscall(const.SYS_getppid)
pivot_root = ccall('pivot_root', True, ct.c_int, ct.c_char_p, ct.c_char_p)
_clone = syscall(const.SYS_clone, ct.c_int, ct.c_void_p)
_mount = ccall('mount', True, ct.c_int, ct.c_char_p, ct.c_char_p, ct.c_char_p, ct.c_ulong, ct.c_void_p)
umount = ccall('umount', True, ct.c_int, ct.c_char_p)
umount2 = ccall('umount2', True, ct.c_int, ct.c_char_p, ct.c_int)
_sethostname = ccall('sethostname', True, ct.c_int, ct.c_char_p, ct.c_int)
_gethostname = ccall('gethostname', True, ct.c_int, ct.c_char_p, ct.c_int)

# Convenience wrappers
def clone(flags):
    return _clone(flags, None)

def sethostname(hostname):
    _sethostname(hostname.encode(), len(hostname))

def gethostname():
    buf = ct.create_string_buffer(256)
    _gethostname(buf, 256)
    return buf.value.decode()

def mount(source, target, fs_type, flags = 0, data = None):
    data = data.encode() if data else None
    return _mount(source, target, fs_type, flags, data)

