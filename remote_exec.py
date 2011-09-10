#coding:utf8

'''
Python executor by socket
'''

import errno
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
    mount_simple_dev,
    mount_proc,
    mount_python_lib,
    mount_tmpfs,
    patient_terminate,
    try_kill,
    umount_all,
    wait_for_pid,
)

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
    def __init__(self, socket_file, fs_size=2000, gname=None, uname=None, hostname=None):
        self.fs_size = fs_size
        self.gid = grp.getgrnam(gname).gr_gid
        self.uid = pwd.getpwnam(uname).pw_uid
        self.hostname = hostname

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

            in_data = io.BytesIO()
            continue_reading = True
            while continue_reading:
                data = connection.recv(4096)
                if not data:
                    os._exit(1)
                zeropos = data.find(b'\0')
                if zeropos > -1:
                    data = data[:zeropos]
                    continue_reading = False
                in_data.write(data)

            stuff_to_exec = in_data.getvalue()
            del in_data

            running = True

            out_pipe, in_pipe = os.pipe()
            sock_fd = connection.fileno()

            pid = os.fork()
            if not pid:
                os.setgid(self.gid)
                os.setuid(self.uid)

                os.close(out_pipe)
                os.dup2(in_pipe, sys.stdout.fileno())
                os.dup2(in_pipe, sys.stderr.fileno())

                mem_bytes = 1024*1024*100
                resource.setrlimit(resource.RLIMIT_AS, (mem_bytes, mem_bytes))
                resource.setrlimit(resource.RLIMIT_NPROC, (1,1))

                try:
                    self.exec_worker(stuff_to_exec)
                except:
                    sys.excepthook(*sys.exc_info())
                finally:
                    os._exit(0)

            os.close(in_pipe)

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
            try:
                while running:
                    if wait_for_pid(pid, 1):
                        running = False

                    while True:
                        try:
                            cr, _, _ = select.select([out_pipe], [], [], 0.02)
                        except select.error as exc:
                            if exc.args[0] == errno.EINTR:
                                break
                            raise

                        if not cr:
                            break
                        data = os.read(out_pipe, PIPE_BUF)
                        if not data:
                            break
                        connection.send(data)
            finally:
                signal.alarm(0)
        except:
            sys.excepthook(*sys.exc_info())
        finally:
            exit(0)

    def exec_worker(self, stuff_to_exec):
        dict_ = dict()
        exec(stuff_to_exec, dict_)

    def start(self):
        tmp = tempfile.mkdtemp()
        mount_tmpfs(self.fs_size, tmp)

        put_old = 'root'
        old_root = os.path.join(tmp, put_old)
        os.mkdir(old_root)

        pylib, pylib_mount = mount_python_lib(tmp)
        ignore_mounts = ['/', '/proc', '/dev', pylib]

        def jail():
            os.environ.clear()

            if self.hostname:
                sethostname(self.hostname)

            pivot_root(tmp, old_root)
            os.chdir('/')

            mount_proc()
            mount_simple_dev()
            umount_all(ignore_mounts)
            os.rmdir('/' + put_old)

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
            umount(pylib_mount)
            umount(tmp)
            os.rmdir(tmp)

if __name__ == '__main__':
    Jail('socket', 2000, 'fluxid', 'fluxid').start()

