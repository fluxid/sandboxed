#coding:utf8

from sandboxed import Jail
from code import interact

class InteractiveJail(Jail):
    def prisoner(self):
        interact()

def main():
    InteractiveJail(2000, 'fluxid', 'fluxid', 'lolnope').run()

if __name__ == '__main__':
    main()

