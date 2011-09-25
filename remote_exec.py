#coding:utf8

'''
Python executor by socket
'''

import errno
import fcntl
import io
import os
import os.path
import resource
import select
import signal
import socket
import sys
import time
import traceback
import errno
import grp
import os
import os.path
import pwd
import signal
import sys
import tempfile

from sandboxed import const
from sandboxed.lowlevel import (
    pivot_root,
    sethostname,
    umount,
)
from sandboxed.utils import (
    clone_and_wait,
    mount_bind,
    mount_proc,
    mount_tmpfs,
    patient_terminate,
    try_kill,
    try_mkdir,
    umount_all,
    wait_for_pid,
)

# Preload stuff
# I gave up on mounting python library, so I have to do some stuff
# to preload modules
'abc'.encode('ANSI_X3.4-1968').decode('ANSI_X3.4-1968')

try:
    PIPE_BUF = select.PIPE_BUF
except AttributeError:
    PIPE_BUF = 512

_old_sigterm = signal.getsignal(signal.SIGTERM)
_old_sigint = signal.getsignal(signal.SIGINT)
def reset_signals():
    signal.signal(signal.SIGTERM, _old_sigterm)
    signal.signal(signal.SIGINT, _old_sigint)

class Jail:
    def __init__(self, socket_file, fs_size=2000, gname=None, uname=None, hostname=None, usr_path=None):
        self.fs_size = fs_size
        self.gid = grp.getgrnam(gname).gr_gid
        self.uid = pwd.getpwnam(uname).pw_uid
        self.hostname = hostname
        self.usr_path = usr_path

        if os.path.exists(socket_file):
            os.remove(socket_file)

        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.bind(socket_file)
        sock.listen(1)
        fd = sock.fileno()
        os.chmod(socket_file, 0o666)

        self.sock_info = sock, fd

    def setup_workers(self):
        sock, fd = self.sock_info

        pids = set()
        running = True

        def wait_for_pids():
            while True:
                try:
                    pid, status = os.waitpid(0, os.WNOHANG)
                except OSError as exc:
                    if exc.errno == errno.ECHILD:
                        break
                    raise
                if pid in pids:
                    pids.remove(pid)
                    print('removing pid: {} status: {} workers: {}'.format(pid, status, len(pids)))

        def handle_signal(signum, frame):
            nonlocal running, pids
            running = False
            for pid in pids:
                print('SIGTERM pid: {}'.format(pid))
                os.kill(pid, signal.SIGTERM)
            time.sleep(0.2)
            wait_for_pids()
            if pids:
                for pid in pids:
                    print('SIGKILL pid: {}'.format(pid))
                    os.kill(pid, signal.SIGKILL)
                time.sleep(0.2)
                wait_for_pids()

        signal.signal(signal.SIGTERM, handle_signal)
        signal.signal(signal.SIGINT, handle_signal)

        try:
            while running:
                wait_for_pids()

                try:
                    if len(pids) < 5 and select.select([fd], [], [], 0.02)[0]:
                        conn, _ = sock.accept()
                        pid = os.fork()
                        if pid:
                            pids.add(pid)
                            print('adding pid: {} workers: {}'.format(pid, len(pids)))
                        else:
                            self.process_connection(conn)
                    else:
                        time.sleep(0.02)
                except select.error as exc:
                    if exc.args[0] == errno.EINTR:
                        break
                    raise
        finally:
            sock.close()

    def process_connection(self, connection):
        pid = None

        def exit(status):
            if pid:
                patient_terminate(pid)
            connection.send(b'\0')
            connection.close()
            os._exit(status)

        try:
            reset_signals()

            running = True

            in_r_pipe, in_w_pipe = os.pipe()
            out_r_pipe, out_w_pipe = os.pipe()
            sock_fd = connection.fileno()

            pid = os.fork()
            if not pid:
                os.setgid(self.gid)
                os.setuid(self.uid)

                os.close(in_w_pipe)
                os.dup2(in_r_pipe, sys.stdin.fileno())

                os.close(out_r_pipe)
                os.dup2(out_w_pipe, sys.stdout.fileno())
                os.dup2(out_w_pipe, sys.stderr.fileno())

                mem_bytes = 1024*1024*100
                resource.setrlimit(resource.RLIMIT_AS, (mem_bytes, mem_bytes))
                resource.setrlimit(resource.RLIMIT_NPROC, (1,1))

                try:
                    os.execv('/usr/bin/python', ('/usr/bin/python', '/usr/bin/main.py'))
                except:
                    sys.excepthook(*sys.exc_info())
                    os._exit(1)

            os.close(out_w_pipe)
            os.close(in_r_pipe)

            def handle_signal(signum, frame):
                if signum == signal.SIGALRM:
                    connection.send(b'Six seconds of execution passed, giving up')
                else:
                    connection.send(b'Signal received')
                exit(1)

            signal.signal(signal.SIGALRM, handle_signal)
            signal.signal(signal.SIGTERM, handle_signal)
            signal.signal(signal.SIGINT, handle_signal)

            signal.alarm(6)
            continue_reading = True
            continue_writing = True
            try:
                while running:
                    if wait_for_pid(pid, 1):
                        running = False

                    while continue_writing:
                        try:
                            cr, cw, _ = select.select([connection], [in_w_pipe], [], 0.02)
                        except select.error as exc:
                            if exc.args[0] == errno.EINTR:
                                break
                            raise
                        if not (cr and cw):
                            break

                        data = connection.recv(PIPE_BUF)
                        if not data:
                            # Socket disconnected, give up
                            exit(1)

                        zeropos = data.find(b'\0')
                        if zeropos > -1:
                            data = data[:zeropos]
                            continue_writing = False

                        os.write(in_w_pipe, data)
                        if not continue_writing:
                            os.close(in_w_pipe)

                    while continue_reading:
                        try:
                            cr, cw, _ = select.select([out_r_pipe], [connection], [], 0.02)
                        except select.error as exc:
                            if exc.args[0] == errno.EINTR:
                                break
                            raise
                        if not (cr and cw):
                            break

                        data = os.read(out_r_pipe, PIPE_BUF)
                        if not data:
                            continue_reading = False
                            break

                        connection.send(data)
            finally:
                signal.alarm(0)
        except:
            sys.excepthook(*sys.exc_info())
        finally:
            exit(0)

    def start(self):
        tmp = tempfile.mkdtemp()
        mount_tmpfs(self.fs_size, tmp)

        put_old = 'root'
        old_root = os.path.join(tmp, put_old)
        os.mkdir(old_root)

        usr_mount = os.path.join(tmp, 'usr')
        try_mkdir(usr_mount)
        flags = const.MS_NODEV | const.MS_NOSUID | const.MS_NOATIME
        mount_bind(self.usr_path, usr_mount, flags)
        flags |= const.MS_REMOUNT | const.MS_RDONLY
        mount_bind(self.usr_path, usr_mount, flags)
        ignore_mounts = ['/', '/proc', '/usr']

        def jail():
            os.environ.clear()
            os.environ.update(
                PATH = '/usr/bin',
                HOME = '/',
            )

            if self.hostname:
                sethostname(self.hostname)

            pivot_root(tmp, old_root)
            os.chdir('/')

            mount_proc()
            umount_all(ignore_mounts)
            os.rmdir('/' + put_old)
            
            os.symlink('/usr/lib', '/lib')
            os.symlink('/usr/lib', '/lib64')

            mount_tmpfs(self.fs_size, '/', const.MS_REMOUNT | const.MS_RDONLY)

            self.setup_workers()

        try:
            pid = clone_and_wait(
                jail,
                const.CLONE_NEWNS |
                const.CLONE_NEWPID |
                const.CLONE_NEWUTS |
                const.CLONE_NEWNET |
                const.CLONE_NEWIPC
            )
        finally:
            umount(usr_mount)
            umount(tmp)
            os.rmdir(tmp)

if __name__ == '__main__':
    Jail('socket', 2000, 'fluxid', 'fluxid', 'lolnope', '/home/fluxid/main/py32mod').start()

