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
_pivot_root = ccall('pivot_root', True, ct.c_int, ct.c_char_p, ct.c_char_p)
_clone = syscall(const.SYS_clone, ct.c_int, ct.c_void_p)
#_clone = ccall('clone', True, ct.c_int, ct.c_void_p, ct.c_void_p, ct.c_int, ct.c_void_p)
_mount = ccall('mount', True, ct.c_int, ct.c_char_p, ct.c_char_p, ct.c_char_p, ct.c_ulong, ct.c_void_p)
_umount = ccall('umount', True, ct.c_int, ct.c_char_p)
_umount2 = ccall('umount2', True, ct.c_int, ct.c_char_p, ct.c_int)
_sethostname = ccall('sethostname', True, ct.c_int, ct.c_char_p, ct.c_int)
_gethostname = ccall('gethostname', True, ct.c_int, ct.c_char_p, ct.c_int)

#_CLONE_CALLBACK = ct.CFUNCTYPE(ct.c_int, ct.c_void_p)
#_CLONE_STACK_SIZE = 65535
#_CloneStack = ct.c_char * _CLONE_STACK_SIZE

# Convenience wrappers
def clone(flags):
    return _clone(flags, None)

#def clone(callback, flags):
#    callback = lambda x: callback() or 0
#    callback_p = _CLONE_CALLBACK(callback)
#    child_stack = _CloneStack()
#    child_stack_p = ct.pointer(ct.pointer(child_stack)[_CLONE_STACK_SIZE-1])
#    pid = _clone(callback_p, child_stack_p, flags, None)
#    os.waitpid(pid, 0)

def sethostname(hostname):
    _sethostname(hostname.encode(), len(hostname))

def gethostname():
    buf = ct.create_string_buffer(256)
    _gethostname(buf, 256)
    return buf.value.decode()

def mount(source, target, fs_type, flags = 0, data = None):
    if isinstance(source, str):
        source = source.encode()
    if isinstance(target, str):
        target = target.encode()
    if isinstance(fs_type, str):
        fs_type = fs_type.encode()
    if isinstance(data, str):
        data = data.encode()
    data = data or None
    return _mount(source, target, fs_type, flags, data)

def umount(target):
    if isinstance(target, str):
        target = target.encode()
    return _umount(target)

def umount2(target, flags):
    if isinstance(target, str):
        target = target.encode()
    return _umount2(target, flags)

def pivot_root(new_root, put_old):
    if isinstance(new_root, str):
        new_root = new_root.encode()
    if isinstance(put_old, str):
        put_old = put_old.encode()
    return _pivot_root(new_root, put_old)

