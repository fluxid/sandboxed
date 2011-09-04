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

from sandboxed import Jail
from sandboxed.utils import mount_python_lib
from sandboxed.lowlevel import umount

class ExecJail(Jail):
    def __init__(self, socket_file, *args, **kwargs):
        if os.path.exists(socket_file):
            os.remove(socket_file)

        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.bind(socket_file)
        sock.listen(1)
        fd = sock.fileno()
        os.chmod(socket_file, 0o666)

        self.sock_info = sock, fd

        super(ExecJail, self).__init__(*args, **kwargs)

    def setup_fs(self, path):
        pylib, pylib_mount = mount_python_lib(path)
        self.pylib_mount = pylib_mount
        self.ignore_mounts = self.ignore_mounts or []
        self.ignore_mounts.append(pylib)

    def teardown_fs(self, path):
        umount(self.pylib_mount)

    def setup_jail(self):
        os.environ.clear()

    def prisoner(self):
        sock, fd = self.sock_info

        pids = set()
        running = True

        def wait_for_pids():
            if pids:
                while True:
                    try:
                        pid, _ = os.waitpid(0, os.WNOHANG)
                    except OSError as exc:
                        if exc.errno == errno.ECHILD:
                            break
                        raise
                    if pid in pids:
                        print('removing pid {}'.format(pid))
                        pids.remove(pid)

        def handle_signal(signum, frame):
            nonlocal running, pids
            running = False
            for pid in pids:
                print('SIGTERM pid {}'.format(pid))
                os.kill(pid, signal.SIGTERM)
            time.sleep(0.2)
            wait_for_pids()
            if pids:
                for pid in pids:
                    print('SIGKILL pid {}'.format(pid))
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
                            print('adding pid {}'.format(pid))
                            pids.add(pid)
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
        try:
            resource.setrlimit(resource.RLIMIT_NPROC, (1,1))
            mem_bytes = 1024*1024*5
            resource.setrlimit(resource.RLIMIT_AS, (mem_bytes, mem_bytes))
            resource.setrlimit(resource.RLIMIT_CPU, (3, 7))

            def handle_signal(signum, frame):
                if signum == signal.SIGALRM:
                    raise Exception('Six seconds of execution passed, giving up')
                elif signum == signal.SIGXCPU:
                    raise Exception('Three seconds of CPU time passed, giving up')
                else:
                    os._exit(1)

            signal.signal(signal.SIGALRM, handle_signal)
            signal.signal(signal.SIGXCPU, handle_signal)
            signal.signal(signal.SIGTERM, handle_signal)
            signal.signal(signal.SIGINT, handle_signal)

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

            old_stdout, old_stderr = sys.stdout, sys.stderr
            sys.stdout = sys.stderr = io.StringIO()

            signal.alarm(6)
            try:
                globals_ = dict()
                exec(in_data.getvalue(), globals_)
            except:
                exception = traceback.print_exc()
            finally:
                signal.alarm(0)
            
            connection.send(sys.stdout.getvalue().encode('utf-8') + b'\0')
        finally:
            sys.stdout = sys.stderr = old_stdout, old_stderr
            connection.close()
            os._exit(0)

def main():
    ExecJail('socket', 2000, 'fluxid', 'fluxid', 'lolnope', remount_ro=False, mount_dev=True).run()

if __name__ == '__main__':
    main()

