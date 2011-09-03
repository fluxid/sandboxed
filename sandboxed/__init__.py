#coding:utf8

import errno
import grp
import os
import os.path
import pwd
import signal
import sys
import tempfile

from sandboxed.lowlevel import clone, sethostname, getpid, umount, pivot_root
from sandboxed import const
from sandboxed.utils import mount_bind, mount_tmpfs, mount_proc, mount_cgroup, umount_all

class Jail:
    def __init__(self, fs_size=2000, gname=None, uname=None, hostname=None):
        self.fs_size = fs_size
        self.gname = gname
        self.uname = uname
        self.hostname = hostname

    def setup_fs(self, path):
        '''
        Setup filesystem before entering jail
        '''
        pass

    def setup_jail(self):
        '''
        Setup jail before changing gid/uid and remounting filesystem r/o
        '''
        pass

    def prisoner(self):
        '''
        Code to be run while being in jail.
        '''
        pass

    def run(self):
        '''
        Set ups jail and runs prisoner
        '''
        # Get desired gid and uid
        gid = None
        uid = None
        if self.gname:
            gid = grp.getgrnam(self.gname).gr_gid
        if self.uname:
            uid = pwd.getpwnam(self.uname).pw_uid

        # Create temporary mountpoint for tmpfs
        tmp = tempfile.mkdtemp()

        # Mount tmpfs for our use
        mount_tmpfs(self.fs_size, tmp)

        # Create directory for old root
        put_old = 'root'
        old_root = os.path.join(tmp, put_old)
        os.mkdir(old_root)

        # Copy stuff to tmpfs
        self.setup_fs(tmp)

        # Clone and create new namespaces. Note CLONE_NEWUSER is not used (yet?)
        pid = clone(
            const.CLONE_NEWNS |
            const.CLONE_NEWPID |
            const.CLONE_NEWUTS |
            const.CLONE_NEWNET |
            const.CLONE_NEWIPC
        )
        assert pid is not None
        if pid:
            while True:
                try:
                    pid2, status = os.waitpid(pid, const.WALL)
                except KeyboardInterrupt:
                    try:
                        os.kill(pid, signal.SIGKILL)
                    except OSError as exc:
                        if exc.errno == errno.ESRCH:
                            break
                        raise
                except OSError as exc:
                    if exc.errno == errno.ECHILD:
                        break
                    raise
                else:
                    if pid2 == pid:
                        break

            # Umount tmpfs and remove mountpoint
            umount(tmp)
            os.rmdir(tmp)
            
            #print('Child {} exited with status {}'.format(pid, status))
            sys.exit(status)
        else:
            # We check if new PID namespace worked
            # Note we use syscall getpid instead of stdlib getpid
            assert getpid() == 1

            # Set desired hostname
            if self.hostname:
                sethostname(self.hostname)

            # Move new root to tmpfs, and old to subdir
            pivot_root(tmp, old_root)
            os.chdir('/')

            # Mount /proc and /cgroup
            mount_proc()
            mount_cgroup()
            
            # Umount all filesystems but those we set up by ourselves
            umount_all(('/', '/proc', '/cgroup'))
            # Remove evidence ;)
            os.rmdir('/' + put_old)

            self.setup_jail()

            # Remount tmpfs r/o
            mount_tmpfs(2000, '/', const.MS_REMOUNT | const.MS_RDONLY)

            # Set to desired gid/uid
            if gid:
                os.setgid(gid)
            if uid:
                os.setuid(uid)
            
            # We're ready to go!
            status = self.prisoner()
            status = int(status) if status else 0
            os._exit(status)

