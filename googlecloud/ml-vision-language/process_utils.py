"""Restart the person detector with exponential back-off after it fails, e.g. when its watchdog exits it.

The watchdog exits the process from C because a hung detector may hold the Python GIL, so the detector cannot restart
itself: supervise() runs the current script again in a child process and restarts that child when it fails.
"""
import os
import signal
import subprocess
import sys
import time

# Set in the child; names the write end of the pipe that report_healthy() writes to
HEALTH_FD_VARIABLE = "SUPERVISOR_HEALTH_FD"
# A child killed by one of these was told to stop by a person or the system, so it is not restarted
STOP_SIGNALS = (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)
# After Ctrl+C, wait this long for the child to clean up before killing it; a hung child ignores SIGINT
SHUTDOWN_SECONDS = 10
# The child's status line may be left on the terminal; clear it before printing over it
CLEAR_LINE = "\r\033[K" if sys.stderr.isatty() else ""


def is_supervised():
    """Whether this process is the child of supervise()."""
    return HEALTH_FD_VARIABLE in os.environ


def report_healthy():
    """Tell the supervisor this child works, so that its next failure restarts the back-off from the shortest wait."""
    if not is_supervised():
        return
    try:
        os.write(int(os.environ[HEALTH_FD_VARIABLE]), b"1")
    except OSError:
        pass  # the supervisor is gone; nobody is left to restart this process anyway


def exit_by_signal(signum):
    """Die by signum instead of exiting with a status.

    A shell loop such as `while true; do ./run_detector.sh; done` only stops on Ctrl+C when the child was killed by
    SIGINT, otherwise it assumes the child handled it and starts another.
    """
    signal.signal(signum, signal.SIG_DFL)
    sys.stdout.flush()  # dying by signal skips Python's exit-time flush of buffered output
    sys.stderr.flush()
    os.kill(os.getpid(), signum)


def supervise(retries, backoff_seconds):
    """Run this script in a child process; restart the child each time it fails, and return the exit status to use.

    Waits backoff_seconds before the first restart and twice as long before each further one: 5, 10, 20, 40, then
    80 seconds for a 5 second back-off. A child that reported healthy before failing starts the count over, so the
    supervisor only gives up after `retries` restarts in a row that failed before their first detection.
    """
    script = os.path.basename(sys.argv[0])
    failures = 0
    child = None

    def forward(signum, frame):
        """Pass `kill -USR1` (stack traces) on to the child; pass SIGTERM and SIGHUP on, then stop the same way."""
        if child is not None:
            child.send_signal(signum)  # does nothing once the child has exited
        if signum != signal.SIGUSR1:
            exit_by_signal(signum)

    for signum in (signal.SIGTERM, signal.SIGHUP, signal.SIGUSR1):
        signal.signal(signum, forward)

    try:
        while True:
            read_fd, write_fd = os.pipe()
            os.set_blocking(read_fd, False)
            # sys.orig_argv keeps interpreter options such as -X; sys.executable is the absolute interpreter path
            child = subprocess.Popen([sys.executable, *sys.orig_argv[1:]], pass_fds=[write_fd],
                                     env={**os.environ, HEALTH_FD_VARIABLE: str(write_fd)})
            os.close(write_fd)
            print(f"Supervisor: started {script} as process {child.pid}", flush=True)
            returncode = child.wait()
            try:
                healthy = os.read(read_fd, 1) == b"1"
            except BlockingIOError:  # nothing written, but a process the child started still holds the pipe open
                healthy = False
            os.close(read_fd)

            if returncode == 0:
                return 0
            if -returncode in STOP_SIGNALS:
                exit_by_signal(-returncode)
            reason = (f"was killed by signal {-returncode} ({signal.strsignal(-returncode)})" if returncode < 0
                      else f"exited with code {returncode}")
            failures = 1 if healthy else failures + 1
            if failures > retries:
                sys.stderr.write(f"{CLEAR_LINE}Supervisor: {script} {reason}; giving up after {retries} restarts "
                                 f"in a row failed before their first detection\n")
                return returncode if returncode > 0 else 128 - returncode  # the shell's status for death by signal
            delay = backoff_seconds * 2 ** (failures - 1)
            sys.stderr.write(f"{CLEAR_LINE}Supervisor: {script} {reason}; restart {failures} of {retries} "
                             f"in {delay:g} s\n")
            time.sleep(delay)
    except KeyboardInterrupt:
        # Ctrl+C reached the child too, as both are in the terminal's foreground process group; let it clean up
        if child is not None:
            try:
                child.wait(timeout=SHUTDOWN_SECONDS)
            except subprocess.TimeoutExpired:
                child.kill()
        exit_by_signal(signal.SIGINT)
