import threading
import time


import config
import tornado_server
import shure
import discover


def main():
    config.config()

    time.sleep(.1)
    threads = [
        threading.Thread(target=shure.WirelessQueryQueue),
        threading.Thread(target=shure.SocketService),
        threading.Thread(target=tornado_server.twisted),
        threading.Thread(target=discover.discover),
        threading.Thread(target=shure.ProcessRXMessageQueue),
    ]

    for t in threads:
        t.start()

    # Keep the main thread alive for the life of the process. If main() returns
    # here, the interpreter begins its shutdown sequence and runs
    # concurrent.futures' atexit handler, which sets a global "shutdown" flag —
    # even though these non-daemon worker threads keep running. After that,
    # Tornado's AsyncHTTPClient can no longer schedule DNS lookups, failing with
    # "cannot schedule new futures after interpreter shutdown" (breaks PCO).
    try:
        for t in threads:
            t.join()
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
