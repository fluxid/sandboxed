#coding:utf8

'''
Convenience utilities to create ctypes funcptrs
'''

import errno
import ctypes as ct
from ctypes.util import find_library
import os

__all__ = (
    'ccall',
    'syscall',
)
libc = ct.CDLL(find_library('c'), use_errno = True)

def errno_check(result, func, arguments):
    '''
    Raises OSError with errno on nonzero ccall return value.

    For use in ccalls which return nonzero value and set errno on error.
    '''
    if result < 0:
        errno_ = ct.get_errno()
        errcode = errno.errorcode.get(errno_)
        if errcode:
            errcode = '{} {}'.format(errcode, os.strerror(errno_))
        else:
            errcode = errno_
        raise OSError(errno_, 'Got nonzero value {} and error "{}" was set'.format(result, errcode))
    return result

def ccall(name, raise_errno, return_type=None, *arg_types):
    '''
    Create a libc function call
    '''
    call = getattr(libc, name)
    call.restype = return_type or None
    call.argtypes = arg_types
    if return_type and raise_errno:
        call.errcheck = errno_check
    return call

def syscall(sys_id, *arg_types):
    '''
    Make a syscall. 
    '''
    def syscall_wrap(*args):
        assert len(arg_types) == len(args)
        sys_args = (atype.from_param(avalue) for atype, avalue in zip(arg_types, args))
        return _syscall(sys_id, *sys_args)
    return syscall_wrap

# We don't use ccall in this case
_syscall = libc.syscall
_syscall.restype = ct.c_int
_syscall.errcheck = errno_check

